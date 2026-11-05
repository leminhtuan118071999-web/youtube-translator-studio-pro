from pathlib import Path
import subprocess,sys,venv,webbrowser
root=Path(__file__).resolve().parent;env=root/'.venv'
py=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
if not py.exists():venv.create(env,with_pip=True)
marker=env/'installed'
if not marker.exists():
 subprocess.run([str(py),'-m','pip','install','youtube-transcript-api==1.2.3'],check=True);marker.write_text('1.2.3')
webbrowser.open('http://127.0.0.1:8505')
subprocess.run([str(py),str(root/'server.py')],check=True)
