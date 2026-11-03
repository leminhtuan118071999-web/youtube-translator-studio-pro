"""One detached render process per immutable run, serialized across projects."""
from __future__ import annotations
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
from uuid import uuid4
from .projects import home, project_dir, atomic, read
from .render import render, Cancelled


def busy(folder):
    path=Path(folder)/'render.lock'
    with path.open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return True
        fcntl.flock(lock,fcntl.LOCK_UN)
    return False


def launch(project):
    folder=project_dir(project['id'])
    with (folder/'render.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Dự án này đang dựng video.') from None
        run_id=uuid4().hex;run=folder/'runs'/run_id;run.mkdir(parents=True)
        atomic(run/'snapshot.json',project)
        atomic(run/'status.json',dict(state='queued',progress=0,stage='Đang chờ dựng',updated=time.time()))
        # Transfer the locked descriptor to the child without a duplicate-start gap.
        try:
            with (run/'worker.log').open('a') as log:
                process=subprocess.Popen([sys.executable,'-m','v3.render_worker',str(run),str(lock.fileno())],
                    cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=log,
                    start_new_session=True,pass_fds=(lock.fileno(),))
            threading.Thread(target=process.wait,daemon=True).start()
            atomic(folder/'latest.json',dict(run_id=run_id,pid=process.pid))
        except Exception as exc:
            atomic(run/'status.json',dict(state='failed',progress=0,stage='Chưa khởi động được renderer',error=str(exc),updated=time.time()))
            raise
    return run_id


def current(folder):
    folder=Path(folder)
    if not (folder/'latest.json').exists(): return None
    ref=read(folder/'latest.json');run=folder/'runs'/ref['run_id'];status=read(run/'status.json')
    if status['state'] in ('queued','running') and not busy(folder):
        status.update(state='interrupted',stage='Tiến trình đã dừng. Có thể dựng lại từ dự án đã lưu.')
    return dict(status,run_id=ref['run_id'],folder=run)


def main(run,fd):
    run=Path(run).resolve();lock=os.fdopen(int(fd),'a')
    # Keep fd alive for the whole run, including cancellation/error cleanup.
    assert lock.fileno() >= 0
    cancel=run/'cancel';caffeine=None;progress=0;last=0
    def update(percent,stage):
        nonlocal progress,last
        progress=max(progress,round(percent))
        if time.monotonic()-last<.5 and percent<100: return
        atomic(run/'status.json',dict(state='running',progress=progress,stage=stage,updated=time.time()))
        last=time.monotonic()
    try:
        if sys.platform=='darwin': caffeine=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
        with (home()/'renderer.lock').open('a') as global_lock:
            while True:
                if cancel.exists(): raise Cancelled()
                try: fcntl.flock(global_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError: time.sleep(.3)
            project=read(run/'snapshot.json')
            details=render(project,project_dir(project['id']),run,update)
            atomic(run/'status.json',dict(state='completed',progress=100,stage='Hoàn thành và đã lưu MP4',details=details,updated=time.time()))
    except Cancelled:
        atomic(run/'status.json',dict(state='cancelled',progress=progress,stage='Đã hủy; dự án gốc vẫn được giữ',updated=time.time()))
    except Exception as exc:
        atomic(run/'status.json',dict(state='failed',progress=progress,stage='Dựng video chưa thành công',error=str(exc)[-3000:],updated=time.time()))
    finally:
        if caffeine: caffeine.terminate()
        lock.close()


if __name__=='__main__': main(sys.argv[1],sys.argv[2])
