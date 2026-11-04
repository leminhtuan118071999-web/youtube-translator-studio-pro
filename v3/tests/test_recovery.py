from v3 import locking as fcntl
import os
import tempfile
import subprocess
import shutil
import time
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from v3 import projects
from v3.render_worker import recover_pending


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,LMT_V3_HOME=self.tmp.name);self.env.start()
        self.project=projects.create('Recovery')
        self.folder=projects.project_dir(self.project['id'])

    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def run_record(self,state='running',reference='latest.json'):
        run=self.folder/'runs'/uuid4().hex;run.mkdir(parents=True)
        projects.atomic(run/'snapshot.json',self.project)
        projects.atomic(run/'status.json',dict(state=state,progress=40,updated=1))
        projects.atomic(run/'task.json',dict(task='render'))
        projects.atomic(self.folder/reference,dict(run_id=run.name,pid=999999))
        return run

    def test_resume_uses_same_snapshot_and_transfers_lock(self):
        run=self.run_record();before=(run/'snapshot.json').read_bytes()
        process=MagicMock(pid=123)
        def spawn(args,**kwargs):
            self.assertIn(str(run),args)
            with (self.folder/'render.lock').open('a') as other:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertTrue(kwargs.get('creationflags')) if os.name=='nt' else self.assertEqual(len(kwargs['pass_fds']),1)
            return process
        with patch('v3.render_worker.subprocess.Popen',side_effect=spawn):
            self.assertEqual(recover_pending(),[run.name])
        self.assertEqual((run/'snapshot.json').read_bytes(),before)
        self.assertEqual(projects.read(self.folder/'latest.json')['pid'],123)
        self.assertEqual(projects.read(run/'status.json')['state'],'queued')

    def test_skip_live_cancelled_failed_and_completed(self):
        for state in ('cancelled','failed','completed'):
            self.run_record(state)
            with patch('v3.render_worker.subprocess.Popen') as spawn:
                self.assertEqual(recover_pending(),[]);spawn.assert_not_called()
        run=self.run_record()
        with (self.folder/'render.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.assertEqual(recover_pending(),[])
        (run/'cancel').touch()
        self.assertEqual(recover_pending(),[])

    def test_newer_completed_run_prevents_resurrecting_old_task(self):
        self.run_record('running','latest-cutout.json')
        old=self.folder/'latest-cutout.json';os.utime(old,(1,1))
        self.run_record('completed','latest.json')
        self.assertEqual(recover_pending(),[])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_recovered_run_finishes_and_exports_without_browser(self):
        clip=self.folder/'assets'/'blue.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=30',
                        '-t','0.3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(clip)],check=True)
        self.project['scenes']=[dict(id='a',name='blue',file='blue.mp4',duration=.3)]
        self.project['export_destination']=str(projects.home()/'exports')
        self.project['export_include_assets']=False
        run=self.run_record()
        self.assertEqual(recover_pending(),[run.name])
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            status=projects.read(run/'status.json')
            if status['state'] in ('completed','failed'):break
            time.sleep(.1)
        self.assertEqual(status['state'],'completed',status)
        self.assertTrue((run/'output.mp4').exists())
        self.assertTrue(list((projects.home()/'exports').glob('*/video.mp4')))
        self.assertEqual(recover_pending(),[])

    def test_spawn_failure_preserves_recoverable_status(self):
        run=self.run_record()
        with patch('v3.render_worker.subprocess.Popen',side_effect=OSError('unavailable')):
            self.assertEqual(recover_pending(),[])
        self.assertEqual(projects.read(run/'status.json')['state'],'running')


if __name__=='__main__':unittest.main()
