import json
import unittest
import uuid
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from persistent_store import (
    backup_state, configured, get_config, load_user, normalize_sessions,
    restore_widget_settings, activate_provider_settings,
    activate_shared_api_settings, remember_widget_settings,
    save_user, settings_from_widgets, snapshot_hash,
    sign_in, refresh_auth,
)


class PersistentStoreTests(unittest.TestCase):
    def setUp(self):
        self.cipher_key = Fernet.generate_key().decode()
        self.secrets = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "public-anon-token",
            "SESSION_ENCRYPTION_KEY": self.cipher_key,
        }
        self.uid = str(uuid.uuid4())
        self.auth = {
            "user_id": self.uid,
            "access_token": "session-jwt", "refresh_token": "refresh-token",
            "expires_at": 99999999999, "email": "me@example.com",
        }

    def test_config_validate_and_no_service_role_needed(self):
        self.assertTrue(configured(self.secrets))
        self.assertEqual(get_config(self.secrets)[0], "https://example.supabase.co")
        self.assertFalse(configured({"SUPABASE_URL": "https://example.supabase.co"}))

    def test_sessions_are_normalized_without_credentials(self):
        ident = uuid.uuid4().hex
        record = {
            "name": "Video 01", "source": "subtitle",
            "translated": "przetłumaczono", "saved_order": 4,
            "job_state": "running", "api_key": "NEVER_SAVE_ME",
        }
        out = backup_state({ident: record}, ident, 4)
        self.assertEqual(out["selected_session"], ident)
        self.assertNotIn("api_key", out["workspaces"][ident])
        self.assertEqual(out["workspaces"][ident]["job_state"], "interrupted")

    def test_running_job_id_survives_saved_profile_for_same_server_reconnect(self):
        ident = uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        snapshot = backup_state({
            ident: {
                "name": "Đang dịch", "source": "Already fetched subtitles",
                "job_state": "running", "job_percent": 45,
                "job_stage": "Đang dịch phần 2/4",
                "job_run_id": run_id,
                "api_key": "NEVER_SAVE_SECRET",
            }
        }, ident, 1)
        record = snapshot["workspaces"][ident]
        self.assertEqual(record["job_run_id"], run_id)
        self.assertEqual(record["job_state"], "interrupted")
        self.assertEqual(record["job_percent"], 45)
        self.assertNotIn("api_key", record)
        self.assertNotIn("NEVER_SAVE_SECRET", json.dumps(snapshot))

    def test_only_api_widget_keys_recovered(self):
        config = {
            "api_provider": "Groq", "api_key_Groq": "groq-super-secret",
            "api_base_Groq": "https://api.groq.com/openai/v1",
            "api_model_id_Groq": "openai/gpt-oss-120b",
            "supadata_api_key_input": "supadata-secret",
            "login_password": "do-not-include",
        }
        settings = settings_from_widgets(config)
        self.assertNotIn("login_password", settings)
        state = {}
        restore_widget_settings(state, settings)
        self.assertEqual(state["api_key_Groq"], "groq-super-secret")
        self.assertEqual(state["supadata_api_key_input"], "supadata-secret")

    def test_third_party_protocol_and_auth_are_retained(self):
        settings = {
            "api_provider": "API bên thứ ba (tùy chỉnh)",
            "api_key_API bên thứ ba (tùy chỉnh)": "private-token",
            "api_base_API bên thứ ba (tùy chỉnh)": "https://api.example.net/v1",
            "api_model_id_API bên thứ ba (tùy chỉnh)": "unique-model",
            "api_format_API bên thứ ba (tùy chỉnh)": "Anthropic Messages",
            "api_auth_mode_API bên thứ ba (tùy chỉnh)": "x-api-key",
        }
        saved = settings_from_widgets(settings)
        restored = {}
        restore_widget_settings(restored, saved)
        self.assertEqual(settings_from_widgets(restored), settings)
        self.assertEqual(restored["_retained_api_settings"], settings)


    def test_provider_keys_survive_switching_and_inactive_widget_cleanup(self):
        state = {
            "api_provider": "Groq", "api_key_Groq": "old-groq-secret",
            "api_model_id_Groq": "groq-model",
            "supadata_api_key_input": "subtitle-secret",
        }
        remember_widget_settings(state)
        # Simulate Streamlit deleting the previous provider's widget keys.
        del state["api_key_Groq"]
        del state["api_model_id_Groq"]
        state["api_provider"] = "Google Gemini"
        state["api_key_Google Gemini"] = "gemini-secret"
        remember_widget_settings(state)
        self.assertEqual(
            settings_from_widgets(state)["api_key_Groq"], "old-groq-secret"
        )
        activate_provider_settings(state, "Groq")
        self.assertEqual(state["api_key_Groq"], "old-groq-secret")
        self.assertEqual(state["api_model_id_Groq"], "groq-model")
        self.assertEqual(state["api_key_Google Gemini"], "gemini-secret")
        self.assertEqual(state["supadata_api_key_input"], "subtitle-secret")

    def test_switching_pages_restores_supadata_and_selected_provider(self):
        state = {
            "api_provider": "Google Gemini",
            "supadata_api_key_input": "supadata-key",
            "api_key_Google Gemini": "gemini-key",
            "api_model_id_Google Gemini": "gemini-2.5-flash",
        }
        remember_widget_settings(state)
        del state["api_provider"]
        del state["supadata_api_key_input"]
        del state["api_key_Google Gemini"]
        del state["api_model_id_Google Gemini"]
        activate_shared_api_settings(state)
        self.assertEqual(state["api_provider"], "Google Gemini")
        self.assertEqual(state["supadata_api_key_input"], "supadata-key")
        activate_provider_settings(state, state["api_provider"])
        self.assertEqual(state["api_key_Google Gemini"], "gemini-key")
        self.assertEqual(
            state["api_model_id_Google Gemini"], "gemini-2.5-flash"
        )
        # A newly entered provider / key always wins over the saved value.
        state["api_provider"] = "Groq"
        state["supadata_api_key_input"] = ""
        activate_shared_api_settings(state)
        self.assertEqual(state["api_provider"], "Groq")
        self.assertEqual(state["supadata_api_key_input"], "")

    def test_update_and_clear_credentials_override_old_retained_values(self):
        state = {}
        restore_widget_settings(state, {
            "api_key_Groq": "original-key",
            "api_base_Groq": "https://api.groq.com/openai/v1",
            "api_provider": "Groq",
            "supadata_api_key_input": "original-subtitle-key",
            "login_password": "NEVER_RESTORE",
        })
        self.assertNotIn("login_password", state)
        state["api_key_Groq"] = "replacement-key"
        state["supadata_api_key_input"] = ""
        state["api_base_Groq"] = "https://example.org/v1"
        remember_widget_settings(state)
        self.assertEqual(settings_from_widgets(state)["api_key_Groq"], "replacement-key")
        self.assertEqual(settings_from_widgets(state)["supadata_api_key_input"], "")
        self.assertEqual(settings_from_widgets(state)["api_base_Groq"], "https://example.org/v1")
        self.assertNotIn("login_password", settings_from_widgets(state))

    @patch("persistent_store._request")
    def test_save_encrypts_keys_and_uses_account_jwt(self, call):
        ident = uuid.uuid4().hex
        content = backup_state(
            {ident: {"name": "Phiên 1", "translated": "test"}}, ident, 1
        )
        settings = {
            "api_key_Groq": "SENSITIVE_API_TOKEN_123",
            "api_key_OpenAI": "OPENAI_API_TOKEN_999",
        }
        save_user(self.secrets, self.auth, content, settings)
        args, kwargs = call.call_args
        self.assertIn("/rest/v1/youtube_studio_state", args[1])
        self.assertEqual(args[2]["Authorization"], "Bearer session-jwt")
        posted = kwargs["json"][0]
        self.assertEqual(posted["user_id"], self.uid)
        self.assertNotIn("SENSITIVE_API_TOKEN_123", repr(posted))
        self.assertNotIn("OPENAI_API_TOKEN_999", repr(posted))
        self.assertNotIn("api_key_Groq", repr(posted["payload"]))
        deciphered = Fernet(self.cipher_key.encode()).decrypt(
            posted["encrypted_config"].encode()
        )
        self.assertEqual(json.loads(deciphered)["api_key_Groq"], "SENSITIVE_API_TOKEN_123")

    @patch("persistent_store._request")
    def test_load_decrypts_per_account_settings(self, call):
        ident = uuid.uuid4().hex
        profile = backup_state({
            ident: {"name": "My translated video", "translated": "text"}
        }, ident, 1)
        encrypted = Fernet(self.cipher_key.encode()).encrypt(
            json.dumps({"api_key_Groq": "restored token"}).encode()
        ).decode()
        call.return_value = [{
            "payload": profile, "encrypted_config": encrypted
        }]
        data, settings = load_user(self.secrets, self.auth)
        self.assertEqual(settings["api_key_Groq"], "restored token")
        self.assertEqual(data["selected_session"], ident)
        self.assertEqual(call.call_args.kwargs["params"]["user_id"], "eq." + self.uid)

    def test_hash_deterministic_and_changes_with_keys(self):
        profile = {"workspaces": {}}
        a = snapshot_hash(profile, {"api_key_Groq": "one"})
        b = snapshot_hash(profile, {"api_key_Groq": "one"})
        c = snapshot_hash(profile, {"api_key_Groq": "two"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    @patch("persistent_store._request")
    def test_publishable_key_is_not_sent_as_bearer(self, call):
        self.secrets["SUPABASE_ANON_KEY"] = "sb_publishable_abc123"
        call.return_value = {
            "user": {"id": self.uid, "email": "me@example.com"},
            "access_token": "fake-access",
            "refresh_token": "fake-refresh",
            "expires_in": 3600,
        }
        sign_in(self.secrets, "me@example.com", "password")
        headers = call.call_args.args[2]
        self.assertEqual(headers["apikey"], "sb_publishable_abc123")
        self.assertNotIn("Authorization", headers)

    def test_secret_key_cannot_bypass_row_security(self):
        self.secrets["SUPABASE_ANON_KEY"] = "sb_secret_must_not_use"
        with self.assertRaises(ValueError):
            get_config(self.secrets)

    @patch("persistent_store._request")
    def test_login_uses_auth_endpoint(self, call):
        call.return_value = {
            "user": {"id": self.uid, "email": "me@example.com"},
            "access_token": "fake-access",
            "refresh_token": "fake-refresh",
            "expires_in": 3600,
        }
        auth = sign_in(self.secrets, "me@example.com", "the-password")
        self.assertEqual(auth["user_id"], self.uid)
        self.assertEqual(call.call_args.kwargs["json"]["password"], "the-password")

    def test_oversized_text_is_rejected(self):
        ident = uuid.uuid4().hex
        with self.assertRaises(ValueError):
            backup_state({ident: {
                "name": "Too long", "source": "z" * 400001
            }}, ident, 1)


if __name__ == "__main__":
    unittest.main()
