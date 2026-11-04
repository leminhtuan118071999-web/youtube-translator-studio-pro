"""Small frozen setup UI; runtime and app code are installed alongside it."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import zipfile

URL='http://127.0.0.1:8503'
FFMPEG_URL='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
APP=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]
DATA=Path(os.getenv('LOCALAPPDATA',Path.home()/'AppData/Local'))/'LMTStudioPro/V3'
HIDDEN=0x08000000 if os.name=='nt' else 0


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def download(url,path,notify):
    partial=path.with_suffix('.part')
    try:
        with urllib.request.urlopen(url,timeout=45) as response,partial.open('wb') as output:
            total=int(response.headers.get('Content-Length','0'));size=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>400*1024*1024:raise RuntimeError('Gói tải vượt kích thước dự kiến.')
                output.write(chunk)
                notify(f'Đang tải FFmpeg: {size//1048576} MB'+(f' / {total//1048576} MB' if total else ''))
        partial.replace(path)
    finally:partial.unlink(missing_ok=True)


def ffmpeg_setup(notify):
    folder=DATA/'tools';folder.mkdir(parents=True,exist_ok=True)
    executable=folder/'ffmpeg.exe'
    if executable.exists() and (folder/'ffprobe.exe').exists():
        try:
            result=subprocess.run([str(executable),'-hide_banner','-filters'],capture_output=True,text=True,creationflags=HIDDEN,timeout=20)
            if result.returncode==0 and ' subtitles ' in result.stdout:return folder
        except (OSError,subprocess.TimeoutExpired):pass
    archive=folder/'ffmpeg.zip'
    notify('Đang kiểm tra gói FFmpeg từ gyan.dev…')
    with urllib.request.urlopen(FFMPEG_URL+'.sha256',timeout=30) as response:
        digest=response.read(4096).decode().split()[0].lower()
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise RuntimeError('Không đọc được mã kiểm tra FFmpeg.')
    download(FFMPEG_URL,archive,notify)
    with archive.open('rb') as handle:
        actual=hashlib.file_digest(handle,'sha256').hexdigest()
    if actual!=digest:
        archive.unlink(missing_ok=True)
        raise RuntimeError('Mã kiểm tra FFmpeg không khớp. Hãy thử lại; gói nguồn có thể vừa cập nhật.')
    with zipfile.ZipFile(archive) as package:
        for name in ('ffmpeg.exe','ffprobe.exe'):
            matches=[entry for entry in package.infolist() if entry.filename.endswith('/bin/'+name)]
            if len(matches)!=1:raise RuntimeError('Gói FFmpeg không đủ thành phần.')
            with package.open(matches[0]) as source,(folder/(name+'.new')).open('wb') as target:shutil.copyfileobj(source,target)
            (folder/(name+'.new')).replace(folder/name)
    archive.unlink(missing_ok=True)
    result=subprocess.run([str(executable),'-hide_banner','-filters'],capture_output=True,text=True,creationflags=HIDDEN,timeout=20)
    if result.returncode or ' subtitles ' not in result.stdout:raise RuntimeError('FFmpeg thiếu bộ lọc phụ đề libass.')
    (folder/'SOURCE.txt').write_text('FFmpeg download: '+FFMPEG_URL+'\nLicense/source: https://www.gyan.dev/ffmpeg/builds/\nSHA256: '+digest+'\n',encoding='utf-8')
    return folder


def server_ready():
    try:
        info=json.loads((DATA/'windows-server.json').read_text(encoding='utf-8'))
        kernel=ctypes.windll.kernel32
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x1000,False,int(info['pid']))
        if not handle:return False
        try:
            code=ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value!=259:return False
        finally:ctypes.windll.kernel32.CloseHandle(handle)
        with urllib.request.urlopen(URL+'/_stcore/health',timeout=2) as response:return response.status==200
    except (OSError,ValueError,KeyError):return False


def runtime_check(notify):
    python=APP/'runtime'/'python.exe'
    command=[str(python),'-c','import onnxruntime, av, faster_whisper, streamlit']
    result=subprocess.run(command,capture_output=True,creationflags=HIDDEN,cwd=APP)
    if result.returncode==0:return
    notify('Đang kiểm tra Microsoft Visual C++ Runtime…')
    package=DATA/'tools'/'vc_redist.x64.exe'
    download('https://aka.ms/vs/17/release/vc_redist.x64.exe',package,notify)
    env=dict(os.environ,LMT_VC_PACKAGE=str(package))
    verification=subprocess.run(['powershell.exe','-NoProfile','-Command',
        "$s=Get-AuthenticodeSignature -LiteralPath $env:LMT_VC_PACKAGE; if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Microsoft Corporation'){exit 0}else{exit 1}"],
        env=env,capture_output=True,creationflags=HIDDEN)
    if verification.returncode:raise RuntimeError('Không xác minh được chữ ký Microsoft của Visual C++ Runtime.')
    notify('Windows có thể hỏi quyền cài Microsoft Visual C++ Runtime. Hoàn thành cửa sổ đó để tiếp tục.')
    code=ctypes.windll.shell32.ShellExecuteW(None,'runas',str(package),'/install /passive /norestart',None,1)
    if code<=32:raise RuntimeError('Chưa cài được Visual C++ Runtime. Mở bộ cài Microsoft trong thư mục dữ liệu rồi thử lại.')
    for _ in range(120):
        result=subprocess.run(command,capture_output=True,creationflags=HIDDEN,cwd=APP)
        if result.returncode==0:return
        time.sleep(2)
    raise RuntimeError('Runtime chưa sẵn sàng. Khởi động lại Windows nếu Microsoft yêu cầu, rồi mở V3.')


def start_server(notify,tools):
    if server_ready():return
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH'):env.pop(key,None)
    env.update(PATH=str(tools)+os.pathsep+env.get('PATH',''),PYTHONUTF8='1',LMT_V3_HOME=str(DATA),
               HF_HOME=str(DATA/'models'/'huggingface'),U2NET_HOME=str(DATA/'models'/'rembg'))
    runtime=APP/'runtime'/'pythonw.exe'
    if not runtime.is_file():raise RuntimeError('Thiếu runtime. Hãy cài lại LMT Studio V3.')
    with (DATA/'windows-server.log').open('a',encoding='utf-8') as log:
        process=subprocess.Popen([str(runtime),'-m','v3.windows_runtime'],cwd=APP,env=env,stdout=log,stderr=log,
                                 creationflags=HIDDEN|0x00000200)
    notify('Đang mở V3 và khôi phục dự án bị gián đoạn…')
    for _ in range(90):
        if server_ready():return
        if process.poll() is not None:raise RuntimeError('V3 chưa khởi động được. Xem windows-server.log trong thư mục dữ liệu.')
        time.sleep(1)
    raise RuntimeError('Khởi động lâu hơn dự kiến. Chờ thêm rồi bấm Mở V3; không cần cài lại.')


def main():
    if os.name!='nt':raise SystemExit('Bộ cài này dành cho Windows x64.')
    DATA.mkdir(parents=True,exist_ok=True)
    # Serialize multiple shortcut clicks without stopping any running renderer.
    ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
    mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\LMTStudioV3Setup')
    if ctypes.windll.kernel32.GetLastError()==183:return
    if '--background' in sys.argv:
        if (DATA/'setup-complete.json').exists():
            try:start_server(lambda value:None,DATA/'tools')
            except Exception:
                (DATA/'startup-error.txt').write_text('Chưa tự mở được V3. Mở shortcut LMT Studio V3 để kiểm tra.',encoding='utf-8')
        return
    import tkinter as tk
    from tkinter import ttk,filedialog
    window=tk.Tk();window.title('LMT Studio V3 · Thiết lập Windows');window.geometry('640x420');window.minsize(580,400)
    panel=ttk.Frame(window,padding=24);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='LMT Studio V3',font=('Segoe UI',22,'bold')).pack(anchor='w')
    ttk.Label(panel,text='Dựng video trên máy của bạn · Windows 10/11 x64').pack(anchor='w',pady=(4,16))
    ttk.Label(panel,text='Thư mục lưu video mặc định').pack(anchor='w')
    config_path=DATA/'windows-preferences.json'
    try:preferences=json.loads(config_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):preferences={}
    destination=tk.StringVar(value=preferences.get('export_folder',str(Path.home()/'Videos'/'LMT Studio V3')))
    row=ttk.Frame(panel);row.pack(fill='x',pady=6)
    ttk.Entry(row,textvariable=destination).pack(side='left',fill='x',expand=True)
    def choose():
        value=filedialog.askdirectory(parent=window)
        if value:destination.set(value)
    ttk.Button(row,text='Chọn…',command=choose).pack(side='right',padx=(8,0))
    ttk.Label(panel,text='Khóa Pixabay riêng (tùy chọn; để trống để giữ khóa đã lưu)').pack(anchor='w',pady=(8,0))
    key=tk.StringVar();ttk.Entry(panel,textvariable=key,show='•').pack(fill='x',pady=6)
    ttk.Label(panel,text='Lần đầu cần mạng tải FFmpeg. Model tách nền/giọng đọc\nsẽ được tải khi bạn dùng chức năng đó.',wraplength=570).pack(anchor='w',pady=8)
    status=tk.StringVar(value='Sẵn sàng thiết lập. Không cần cài Python hoặc dùng Terminal.')
    ttk.Label(panel,textvariable=status,wraplength=570).pack(anchor='w',pady=8)
    events=queue.Queue()
    def work(folder_value,key_value):
        try:
            folder=Path(folder_value).expanduser();folder.mkdir(parents=True,exist_ok=True)
            if not folder.is_absolute():raise RuntimeError('Hãy chọn đường dẫn thư mục đầy đủ.')
            write_json(config_path,dict(export_folder=str(folder)))
            if key_value:write_json(DATA/'pixabay-key.json',dict(key=key_value))
            tools=ffmpeg_setup(lambda text:events.put(('status',text)))
            runtime_check(lambda text:events.put(('status',text)))
            start_server(lambda text:events.put(('status',text)),tools)
            write_json(DATA/'setup-complete.json',dict(version=1))
            events.put(('done','V3 đã sẵn sàng. Có thể đóng cửa sổ này; tác vụ tiếp tục chạy nền.'))
        except Exception as exc:events.put(('error',str(exc)))
    def begin():
        button.config(state='disabled');status.set('Đang thiết lập…')
        threading.Thread(target=work,args=(destination.get().strip(),key.get().strip()),daemon=True).start()
    button=ttk.Button(panel,text='Thiết lập và mở V3',command=begin);button.pack(anchor='w',pady=8)
    def pump():
        try:
            while True:
                kind,value=events.get_nowait();status.set(value)
                if kind in ('done','error'):button.config(state='normal')
                if kind=='done':key.set('');webbrowser.open(URL)
        except queue.Empty:pass
        window.after(100,pump)
    pump();window.mainloop()


if __name__=='__main__':main()
