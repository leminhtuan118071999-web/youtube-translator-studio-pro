"""Run isolated Review Studio without changing V2/V3 environments."""
from pathlib import Path
import subprocess, sys, venv
root=Path(__file__).resolve().parents[1]
env=root/'.venv-review'
python=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
if not python.exists(): venv.create(env,with_pip=True)
requirements=root/'review_app/requirements.txt'
marker=env/'requirements-installed.txt'
if not marker.exists() or marker.read_text()!=requirements.read_text():
    subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True)
    marker.write_text(requirements.read_text())
subprocess.run([str(python),'-m','streamlit','run',str(root/'review_app/app.py'),'--server.address=127.0.0.1','--server.port=8504'],cwd=root,check=True)
