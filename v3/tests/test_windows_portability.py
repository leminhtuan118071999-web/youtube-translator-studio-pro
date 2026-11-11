import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from v3 import projects, locking
from v3.render import run_ffmpeg


class PortabilityTests(unittest.TestCase):
    def test_lock_is_exclusive_across_processes_and_released_on_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lock'
            code="from v3 import locking; import sys; f=open(sys.argv[1],'a'); locking.flock(f,locking.LOCK_EX|locking.LOCK_NB)"
            env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[2]))
            with path.open('a') as handle:
                locking.flock(handle,locking.LOCK_EX)
                result=subprocess.run([sys.executable,'-c',code,str(path)],env=env,capture_output=True)
                self.assertNotEqual(result.returncode,0)
            result=subprocess.run([sys.executable,'-c',code,str(path)],env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_ffmpeg_pipe_progress_finishes(self):
        import shutil
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg required')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);values=[]
            run_ffmpeg(['-f','lavfi','-i','color=blue:s=160x90:r=30','-t','0.2','-an','-c:v','libx264',str(folder/'out.mp4')],
                       folder,folder/'cancel',values.append,duration=.2)
            self.assertTrue((folder/'out.mp4').stat().st_size)

    def test_windows_project_directory_uses_local_app_data(self):
        if os.name!='nt':self.skipTest('Windows path check')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LOCALAPPDATA=tmp):
            with patch.dict(os.environ,{},clear=False):
                original=os.environ.pop('LMT_V3_HOME',None)
                try:self.assertEqual(projects.home(),(Path(tmp)/'LMTStudioPro/V3').resolve())
                finally:
                    if original is not None:os.environ['LMT_V3_HOME']=original


if __name__=='__main__':unittest.main()
