"""Private local Streamlit host for the installed Windows app."""
import os
from pathlib import Path
import sys
from .projects import home, atomic
from . import locking
from .render_worker import recover_pending


def main():
    lock=(home()/'windows-server.lock').open('a')
    try:locking.flock(lock,locking.LOCK_EX|locking.LOCK_NB)
    except BlockingIOError:return
    # A different application on this port must never be mistaken for V3.
    import socket
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8503))==0:
            raise RuntimeError('Cổng 8503 đang được ứng dụng khác sử dụng.')
    atomic(home()/'windows-server.json',dict(pid=os.getpid(),port=8503))
    recover_pending()
    from streamlit.web.cli import main as streamlit_main
    sys.argv=['streamlit','run',str(Path(__file__).with_name('studio_app.py')),
              '--server.address','127.0.0.1','--server.port','8503','--server.headless','true',
              '--server.maxUploadSize','1024','--browser.gatherUsageStats','false']
    try:streamlit_main()
    finally:
        locking.flock(lock,locking.LOCK_UN);lock.close()


if __name__=='__main__':main()
