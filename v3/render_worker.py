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
from .projects import home, project_dir, atomic, read, save, export_run
import shutil
import signal
from .render import render, Cancelled


def busy(folder):
    path=Path(folder)/'render.lock'
    with path.open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return True
        fcntl.flock(lock,fcntl.LOCK_UN)
    return False


def launch(project, task="render"):
    if task not in ("render","transcribe","cutout"):raise ValueError("Tác vụ không hợp lệ.")
    if task=="transcribe" and not project.get("voice"):raise ValueError("Hãy tải file giọng đọc trước.")
    folder=project_dir(project['id'])
    with (folder/'render.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Dự án này đang dựng video.') from None
        run_id=uuid4().hex;run=folder/'runs'/run_id;run.mkdir(parents=True)
        atomic(run/'snapshot.json',project)
        atomic(run/'status.json',dict(state='queued',task=task,progress=0,stage='Đang chờ xử lý',updated=time.time()))
        atomic(run/'task.json',dict(task=task))
        # Transfer the locked descriptor to the child without a duplicate-start gap.
        try:
            with (run/'worker.log').open('a') as log:
                process=subprocess.Popen([sys.executable,'-m','v3.render_worker',str(run),str(lock.fileno())],
                    cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=log,
                    start_new_session=True,pass_fds=(lock.fileno(),))
            threading.Thread(target=process.wait,daemon=True).start()
            atomic(folder/('latest-asr.json' if task=='transcribe' else 'latest-cutout.json' if task=='cutout' else 'latest.json'),dict(run_id=run_id,pid=process.pid))
        except Exception as exc:
            atomic(run/'status.json',dict(state='failed',progress=0,stage='Chưa khởi động được renderer',error=str(exc),updated=time.time()))
            raise
    return run_id


def current(folder, task="render"):
    folder=Path(folder)
    reference=folder/("latest-asr.json" if task=="transcribe" else "latest-cutout.json" if task=="cutout" else "latest.json")
    if not reference.exists(): return None
    ref=read(reference);run=folder/'runs'/ref['run_id'];status=read(run/'status.json')
    if status['state'] in ('queued','running') and not busy(folder):
        status.update(state='interrupted',stage='Tiến trình đã dừng. Có thể dựng lại từ dự án đã lưu.')
    return dict(status,run_id=ref['run_id'],folder=run)


def recognize(project,run,cancel):
    with (run/'speech.log').open('a') as log:
        process=subprocess.Popen([sys.executable,'-m','v3.speech',str(run)],
            cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=log)
        try:
            while process.poll() is None:
                if cancel.exists():raise Cancelled()
                time.sleep(.2)
            if cancel.exists():raise Cancelled()
            if process.returncode:
                error=read(run/'speech-error.json')['error'] if (run/'speech-error.json').exists() else 'Tiến trình nhận diện đã dừng; xem speech.log.'
                raise ValueError(error)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    folder=project_dir(project['id']);latest=read(folder/'project.json')
    if latest.get('voice')!=project['voice']:
        raise ValueError('File giọng đọc đã thay đổi; kết quả nhận diện chưa áp dụng vào dự án.')
    data=read(run/'words.json');prefix=uuid4().hex
    shutil.copy2(run/'captions.srt',folder/'assets'/(prefix+'.srt'))
    shutil.copy2(run/'words.json',folder/'assets'/(prefix+'.json'))
    latest.update(captions=prefix+'.srt',caption_words=prefix+'.json',captions_origin='asr',
                  caption_source_voice=project['voice'],caption_language=data['language'])
    save(latest)
    return dict(language=data['language'],words=len(data['words']),source_voice=project['voice'])


def prepare_story(run,task='render'):
    args=[sys.executable,'-m','v3.story',str(run)]
    if task=='cutout':args.append('cutout')
    with (run/'prepare.log').open('a') as log:
        process=subprocess.Popen(args,cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=log,start_new_session=True)
        try:
            while process.poll() is None:
                if (run/'cancel').exists():raise Cancelled()
                time.sleep(.2)
            if (run/'cancel').exists():raise Cancelled()
            if process.returncode:
                error=read(run/'prepare-error.json')['error'] if (run/'prepare-error.json').exists() else 'Chưa chuẩn bị được nguyên liệu; xem prepare.log.'
                raise ValueError(error)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    return read(run/('cutout-result.json' if task=='cutout' else 'render-project.json'))


def main(run,fd):
    run=Path(run).resolve();lock=os.fdopen(int(fd),'a')
    # Keep fd alive for the whole run, including cancellation/error cleanup.
    assert lock.fileno() >= 0
    cancel=run/'cancel';caffeine=None;progress=0;last=0
    task=read(run/'task.json')['task'] if (run/'task.json').exists() else 'render'
    def update(percent,stage):
        nonlocal progress,last
        progress=max(progress,round(percent))
        if time.monotonic()-last<.5 and percent<100: return
        atomic(run/'status.json',dict(state='running',task=task,progress=progress,stage=stage,updated=time.time()))
        last=time.monotonic()
    try:
        if sys.platform=='darwin': caffeine=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
        with (home()/'renderer.lock').open('a') as global_lock:
            while True:
                if cancel.exists(): raise Cancelled()
                try: fcntl.flock(global_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError: time.sleep(.3)
            project=read(run/'snapshot.json')
            if task=='cutout':
                details=prepare_story(run,'cutout');stage='Đã tách nền; kiểm tra ảnh và bố cục trước khi dựng'
            elif task=='transcribe':
                details=recognize(project,run,cancel)
                stage='Đã tạo phụ đề theo giọng đọc · '+details['language']
            else:
                if project.get('story',{}).get('enabled'):
                    project=prepare_story(run)
                    details=render(project,project_dir(project['id']),run,lambda p,s:update(50+p*.49,'Bước 5/6 · '+s))
                else:details=render(project,project_dir(project['id']),run,update)
                stage='Hoàn thành và đã lưu MP4'
                if project.get('export_destination','').strip():
                    update(99,'Bước 6/6 · Đang lưu kết quả vào thư mục đã chọn')
                    try:
                        details['export_location']=export_run(run,project['export_destination'],project.get('export_include_assets',True))
                        stage='Hoàn thành và đã lưu vào thư mục đã chọn'
                    except (ValueError,OSError,KeyError,TypeError) as exc:
                        details['export_error']=str(exc)
                        stage='MP4 đã hoàn thành; chưa sao chép được vào nơi đã chọn'
            atomic(run/'status.json',dict(state='completed',task=task,progress=100,stage=stage,details=details,updated=time.time()))
    except Cancelled:
        atomic(run/'status.json',dict(state='cancelled',progress=progress,stage='Đã hủy; dự án gốc vẫn được giữ',updated=time.time()))
    except Exception as exc:
        atomic(run/'status.json',dict(state='failed',progress=progress,stage='Dựng video chưa thành công',error=str(exc)[-3000:],updated=time.time()))
    finally:
        if caffeine: caffeine.terminate()
        lock.close()


if __name__=='__main__': main(sys.argv[1],sys.argv[2])
