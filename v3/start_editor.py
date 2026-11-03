#!/usr/bin/env python3
"""Launch a private localhost editor. FFmpeg is installed separately by the user."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parent
ENV=ROOT/'.venv-editor'


def main():
    if sys.version_info<(3,12):raise SystemExit('Cần Python 3.12 trở lên.')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise SystemExit('Chưa có FFmpeg. Trên Mac có Homebrew, chạy: brew install ffmpeg\nSau đó mở lại V3.')
    if not (ENV/'bin/python').exists():venv.create(ENV,with_pip=True)
    python=str(ENV/'bin/python');requirements=ROOT/'requirements.txt'
    marker=ENV/'installed.txt'
    if not marker.exists() or marker.read_text()!=requirements.read_text():
        subprocess.run([python,'-m','pip','install','-r',str(requirements)],check=True)
        marker.write_text(requirements.read_text())
    os.execv(python,[python,'-m','streamlit','run',str(ROOT/'studio_app.py'),
                      '--server.address','127.0.0.1','--server.port','8503','--server.maxUploadSize','1024',
                      '--browser.gatherUsageStats','false'])


if __name__=='__main__':main()
