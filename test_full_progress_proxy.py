import unittest
from unittest.mock import patch
from background_jobs import JobProgress
from server_video_jobs import _FullJobProgressProxy
from groq_pacing import GroqRequestGate

class FullProgressProxyTests(unittest.TestCase):
    def test_progress_snapshot_remains_callable_and_cloud_receives_job_data(self):
        inner = JobProgress()
        job = {'sid':'session'}
        proxy = _FullJobProgressProxy(job, inner)
        proxy.update(25, 'Writing')
        self.assertEqual(proxy.snapshot(), (25, 'Writing'))
        with patch('server_video_jobs.save_cloud_full_checkpoint') as save:
            proxy.publish('translated', 'Story')
            save.assert_called_once_with(job, {'translated':'Story'}, 'running')

    def test_groq_wait_can_report_progress_through_server_save_proxy(self):
        clock = [0.0]
        gate = GroqRequestGate(clock=lambda:clock[0], sleeper=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
        proxy = _FullJobProgressProxy({'sid':'session'}, JobProgress())
        proxy.update(20, 'Writing')
        gate.acquire('key','model','x'*6000,proxy)
        gate.acquire('key','model','x'*6000,proxy)
        self.assertGreaterEqual(clock[0],65)
        self.assertEqual(proxy.snapshot()[0],20)
