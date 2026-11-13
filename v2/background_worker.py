#!/usr/bin/env python3
"""Manage the existing V2 worker as a per-user macOS LaunchAgent."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

LABEL = 'com.lmtstudio.v2.worker'
ROOT = Path(__file__).resolve().parent


def paths():
    home = Path.home()
    return (home/'Library/LaunchAgents'/f'{LABEL}.plist',
            home/'Library/Logs/LMTStudioPro')


def launch_spec(python, root, logs):
    return dict(Label=LABEL,
        ProgramArguments=[str(python),str(root/'start_local_worker.py')],
        WorkingDirectory=str(root.parent),RunAtLoad=True,
        KeepAlive=dict(SuccessfulExit=False),ThrottleInterval=30,
        EnvironmentVariables=dict(LMT_V2_BACKGROUND='1',PYTHONUNBUFFERED='1',
            PATH='/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'),
        StandardOutPath=str(logs/'v2-worker.log'),
        StandardErrorPath=str(logs/'v2-worker-error.log'))


def launchctl(*args):
    return subprocess.run(['/bin/launchctl',*args],capture_output=True,text=True)


def install():
    if sys.version_info < (3,12):
        raise ValueError('Cần Python 3.12 trở lên, giống bản worker hiện tại.')
    if __package__:
        from .start_local_worker import CONFIG_PATH,read_config
    else:
        from start_local_worker import CONFIG_PATH,read_config
    if not CONFIG_PATH.exists():
        raise ValueError('Chạy python3 v2/start_local_worker.py để cấu hình worker trước.')
    read_config(CONFIG_PATH)  # Validate privately; never put secrets in the plist.
    plist,logs=paths()
    plist.parent.mkdir(parents=True,exist_ok=True)
    logs.mkdir(parents=True,exist_ok=True,mode=0o700)
    domain=f'gui/{os.getuid()}'
    target=f'{domain}/{LABEL}'
    content=plistlib.dumps(launch_spec(Path(sys.executable).absolute(),ROOT,logs))
    fd,temporary=tempfile.mkstemp(prefix='.lmt-v2-',dir=plist.parent)
    try:
        with os.fdopen(fd,'wb') as handle:handle.write(content)
        os.chmod(temporary,0o600)
        # Stop only our managed V2 agent, never unrelated apps or V3.
        launchctl('bootout',target)
        os.replace(temporary,plist)
    finally:
        Path(temporary).unlink(missing_ok=True)
    enabled=launchctl('enable',target)
    if enabled.returncode:
        raise ValueError('Chưa bật được dịch vụ V2. Kiểm tra quyền LaunchAgents của tài khoản Mac.')
    result=launchctl('bootstrap',domain,str(plist))
    if result.returncode:
        raise ValueError('Chưa nạp được dịch vụ V2. Có thể chạy lại lệnh cài đặt; cấu hình và phiên vẫn được giữ.')
    print('Đã cài dịch vụ V2 chạy nền và tự khởi động khi đăng nhập Mac.')
    print('Có thể đóng cửa sổ Terminal. Mở V2 tại https://lmt-studio-pro-v2-web.onrender.com')
    print('Dịch vụ đã được nạp; xem nhật ký để xác nhận worker kết nối cơ sở dữ liệu.')
    print(f'Nhật ký: {logs}')
    print('Máy cần còn bật, đăng nhập và có mạng. Màn hình được phép tắt.')


def main():
    parser=argparse.ArgumentParser(description='Chạy worker V2 nền trên Mac, không cần giữ Terminal.')
    parser.add_argument('action',choices=('install','status','stop','uninstall'),nargs='?',default='install')
    action=parser.parse_args().action
    if sys.platform!='darwin':
        raise ValueError('Chức năng chạy nền này dành cho macOS.')
    if action=='install':
        install();return
    target=f'gui/{os.getuid()}/{LABEL}'
    if action=='status':
        result=launchctl('print',target)
        if result.returncode:print('Dịch vụ V2 chưa được nạp. Chạy lại lệnh install.')
        else:
            print('Dịch vụ V2 đã được nạp:')
            for line in result.stdout.splitlines():
                if line.strip().startswith(('state =','pid =','last exit code =')):print(line.strip())
        print('Xác nhận kết nối trong ~/Library/Logs/LMTStudioPro/v2-worker.log')
    else:
        launchctl('bootout',target)
        if action=='uninstall':
            paths()[0].unlink(missing_ok=True)
            print('Đã gỡ tự khởi động V2; giữ nguyên mã nguồn, cấu hình và dữ liệu phiên.')
        else:print('Đã gửi lệnh dừng worker nền V2; tự khởi động vẫn bật cho lần đăng nhập sau.')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError):
        # Never print credentials or raw subprocess/database exceptions.
        print('Chưa hoàn tất thao tác. Kiểm tra macOS, Python 3.12+, cấu hình worker và quyền LaunchAgents.')
        sys.exit(1)
