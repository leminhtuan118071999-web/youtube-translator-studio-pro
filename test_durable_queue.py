"""Durable authenticated queue and independent-worker regression tests."""
import json
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock

from cryptography.fernet import Fernet

import durable_queue
import durable_worker


class DurableQueueTests(unittest.TestCase):
    def setUp(self):
        self.secrets = {
            "SUPABASE_URL":"https://example.supabase.co",
            "SUPABASE_ANON_KEY":"public-anon",
            "SESSION_ENCRYPTION_KEY":Fernet.generate_key().decode(),
            "DURABLE_WORKER_ENABLED":"true",
        }
        self.auth = {"user_id":str(uuid.uuid4()),"access_token":"user-jwt"}
        self.sid = uuid.uuid4().hex

    def test_enqueue_encrypts_provider_credentials_and_uses_own_jwt(self):
        created = str(uuid.uuid4())
        calls = []
        def fake(method,url,headers,**kwargs):
            calls.append((method,url,headers,kwargs))
            return [{"id":created,"session_id":self.sid,
                     "kind":"full","status":"queued"}]
        with patch("durable_queue._request",side_effect=fake):
            got = durable_queue.submit_job(
                self.secrets,self.auth,self.sid,"full",
                {"language":"Tiếng Anh","source":"A long story","provider":"Groq"},
                {"api_key":"secret-GROQ-value","supadata_key":"secret-SUPADATA"},
            )
        self.assertEqual(got,created)
        method,url,headers,kwargs = calls[0]
        self.assertEqual(method,"POST")
        self.assertEqual(headers["Authorization"],"Bearer user-jwt")
        blob = kwargs["json"][0]
        self.assertNotIn("secret-GROQ-value",json.dumps(blob))
        decrypted = Fernet(
            self.secrets["SESSION_ENCRYPTION_KEY"].encode()
        ).decrypt(blob["encrypted_keys"].encode())
        self.assertEqual(json.loads(decrypted)["api_key"],"secret-GROQ-value")
        self.assertEqual(blob["user_id"],self.auth["user_id"])

    def test_payload_rejects_key_leak_and_wrong_session(self):
        with self.assertRaisesRegex(ValueError,"xác thực"):
            durable_queue.submit_job(
                self.secrets,self.auth,self.sid,"full",
                {"api_key":"plaintext"},{"api_key":"secret"},
            )
        with self.assertRaises(ValueError):
            durable_queue.submit_job(
                self.secrets,self.auth,"bad-session","full",
                {},{"api_key":"secret"},
            )

    def test_queue_result_only_updates_linked_session(self):
        own = str(uuid.uuid4())
        other = str(uuid.uuid4())
        sessions = {
            self.sid:{"job_queue_id":own, "translated":"Old", "name":"My video"},
            uuid.uuid4().hex:{"job_queue_id":other,"translated":"Keep"},
        }
        rows = [
            {"id":str(uuid.uuid4()),"session_id":self.sid,"kind":"full",
             "status":"completed","result":{"translated":"WRONG"}},
            {"id":own,"session_id":self.sid,"kind":"full",
             "status":"completed","progress":100,
             "stage":"Complete","result":{"translated":"Right",
                                         "api_key":"DO_NOT_COPY"}},
        ]
        self.assertTrue(durable_queue.apply_owned_job_results(sessions,rows))
        self.assertEqual(sessions[self.sid]["translated"],"Right")
        self.assertNotIn("api_key",sessions[self.sid])
        self.assertEqual(sessions[self.sid]["job_state"],"completed")
        self.assertTrue(sessions[self.sid]["saved"])
        self.assertEqual([v["translated"] for k,v in sessions.items() if k != self.sid],
                         ["Keep"])

    def test_health_rejects_old_heartbeat(self):
        fresh = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
        with patch("durable_queue._request",return_value=[{"last_seen":fresh}]):
            self.assertTrue(durable_queue.worker_healthy(self.secrets,self.auth))
        with patch("durable_queue._request",return_value=[{"last_seen":old}]):
            self.assertFalse(durable_queue.worker_healthy(self.secrets,self.auth))

    def test_encrypted_credentials_unsealed_only_on_worker(self):
        crypt = Fernet(self.secrets["SESSION_ENCRYPTION_KEY"].encode())
        fake_job = {
            "id":str(uuid.uuid4()),"session_id":self.sid,
            "user_id":self.auth["user_id"],"kind":"video_forms",
            "snapshot":{"language":"English","duration_seconds":24,
                        "existing_plan":None},
            "result":{},
            "encrypted_keys":crypt.encrypt(
                b'{"api_key":"SECRET_CLIENT_TEXT_KEY"}'
            ).decode(),
        }
        with patch.dict("os.environ",{
            "SESSION_ENCRYPTION_KEY":self.secrets["SESSION_ENCRYPTION_KEY"],
        }):
            snapshot,keys = durable_worker.build_snapshot(fake_job)
        self.assertEqual(snapshot["api_key"],"SECRET_CLIENT_TEXT_KEY")
        self.assertEqual(keys["api_key"],"SECRET_CLIENT_TEXT_KEY")
        self.assertNotIn("api_key",fake_job["snapshot"])

    def test_worker_claim_uses_skip_locked_and_lease_token(self):
        from pathlib import Path
        source = Path("durable_worker.py").read_text(encoding="utf-8")
        self.assertIn("for update skip locked",source.lower())
        self.assertIn("lease_token=gen_random_uuid()",source)
        self.assertIn("where id=%s and lease_token=%s",source)
        self.assertIn("heartbeat_worker(str(job[",source)
        self.assertIn("retry_wait",source)
        self.assertIn("encrypted_keys=%s",source)

    def test_private_portrait_uri_must_match_own_user_and_session(self):
        import requests
        path=f'{self.auth["user_id"]}/{self.sid}/Ala.png'
        content=b"\x89PNG\r\n\x1a\n" + b"data"
        with patch("requests.get") as get:
            get.return_value=Mock(ok=True,content=content)
            images=durable_queue.fetch_portrait_images(
                self.secrets,self.auth,self.sid,
                json.dumps({"Ala":path,"Attacker":"another/user/path.png"}),
            )
        self.assertEqual(images["Ala"],content)
        self.assertNotIn("Attacker",images)
        self.assertEqual(get.call_count,1)

if __name__=="__main__":
    unittest.main()
