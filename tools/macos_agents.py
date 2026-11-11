#!/usr/bin/env python3
"""Install per-user LMT agents. Run on the Mac, never with sudo."""
import argparse
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys

LABELS = {'v2': 'com.lmtstudio.v2.worker', 'v3': 'com.lmtstudio.v3.editor'}
PATH = '/opt/homebrew/opt/ffmpeg-full/bin:/usr/local/opt/ffmpeg-full/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'


def spec(kind, root, python, logs):
    script = root / ('v2/start_local_worker.py' if kind == 'v2' else 'v3/start_editor.py')
    return {'Label': LABELS[kind], 'ProgramArguments': [str(python), str(script)],
            'WorkingDirectory': str(root), 'RunAtLoad': True, 'KeepAlive': True,
            'ThrottleInterval': 60, 'EnvironmentVariables': {'PATH': PATH, 'PYTHONUNBUFFERED': '1'},
            'StandardOutPath': str(logs / (kind + '.log')),
            'StandardErrorPath': str(logs / (kind + '.error.log'))}


def ctl(*args, check=True):
    return subprocess.run(['/bin/launchctl', *args], check=check, capture_output=True, text=True)


def main():
    p = argparse.ArgumentParser(description='LMT V2 + V3 chạy nền trên Mac sau khi đăng nhập.')
    p.add_argument('action', choices=['install', 'status', 'stop', 'start', 'uninstall'])
    p.add_argument('--v2', type=Path, default=Path.home() / 'lmt-studio-pro-v2')
    p.add_argument('--v3', type=Path, default=Path.home() / 'lmt-video-editor-v3')
    a = p.parse_args()
    if sys.platform != 'darwin' or os.getuid() == 0:
        raise SystemExit('Chạy bằng tài khoản thường trên Mac, không dùng sudo.')
    domain = f'gui/{os.getuid()}'
    agents = Path.home() / 'Library/LaunchAgents'
    logs = Path.home() / 'Library/Logs/LMTStudioPro'
    roots = {'v2': a.v2.expanduser().resolve(), 'v3': a.v3.expanduser().resolve()}
    if a.action == 'install':
        if sys.version_info < (3, 12):
            raise SystemExit('Cần Python 3.12 trở lên.')
        for kind, root in roots.items():
            script = root / ('v2/start_local_worker.py' if kind == 'v2' else 'v3/start_editor.py')
            if not script.is_file():
                raise SystemExit(f'Không tìm thấy {script}. Dùng --v2 hoặc --v3 để chỉ đúng thư mục.')
        if not (Path.home() / 'Library/Application Support/LMTStudioPro/worker.json').is_file():
            raise SystemExit('Chưa có cấu hình V2. Chạy python3 v2/start_local_worker.py --configure trong thư mục V2 trước.')
        # Do not race an existing editor started in Terminal.
        if ctl('print', domain + '/' + LABELS['v3'], check=False).returncode:
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', 8503)) == 0:
                    raise SystemExit('V3 đang mở ở cổng 8503. Dừng V3 bằng Ctrl+C rồi cài lại.')
        # Detect a manually started V2 without displaying process arguments/config.
        processes = subprocess.run(['/bin/ps', '-axo', 'command='], capture_output=True, text=True, check=True).stdout
        if ctl('print', domain + '/' + LABELS['v2'], check=False).returncode and any(
            'start_local_worker.py' in line and '--worker' in line for line in processes.splitlines()
        ):
            raise SystemExit('V2 worker đang chạy trong Terminal. Dừng bằng Ctrl+C rồi cài lại.')
        agents.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(logs, 0o700)
        for kind, root in roots.items():
            dest = agents / (LABELS[kind] + '.plist')
            ctl('bootout', domain + '/' + LABELS[kind], check=False)
            # Keep original venv-aware executable path; resolve() can escape a venv.
            python = Path(os.path.abspath(sys.executable))
            dest.write_bytes(plistlib.dumps(spec(kind, root, python, logs)))
            dest.chmod(0o600)
            ctl('enable', domain + '/' + LABELS[kind])
            ctl('bootstrap', domain, str(dest))
        print('Đã đăng ký V2 và V3. Đang khởi động/cài thư viện nếu cần; kiểm tra bằng status.')
    else:
        for kind, label in LABELS.items():
            target = domain + '/' + label
            dest = agents / (label + '.plist')
            if a.action == 'status':
                result = ctl('print', target, check=False)
                if result.returncode:
                    print(kind.upper() + ': chưa được nạp')
                else:
                    fields = [s.strip() for s in result.stdout.splitlines() if s.strip().startswith(('state =', 'pid =', 'last exit code ='))]
                    print(kind.upper() + ': ' + ', '.join(fields))
            elif a.action in ('stop', 'uninstall'):
                ctl('bootout', target, check=False)
                if a.action == 'uninstall':
                    dest.unlink(missing_ok=True)
                print(kind.upper() + ': đã dừng' + (' và gỡ LaunchAgent' if a.action == 'uninstall' else ' tới khi start hoặc đăng nhập lại'))
            elif a.action == 'start':
                if not dest.is_file():
                    raise SystemExit('Chưa cài LaunchAgent. Chạy install trước.')
                ctl('enable', target)
                if ctl('print', target, check=False).returncode:
                    ctl('bootstrap', domain, str(dest))
                else:
                    ctl('kickstart', target)
    print('V3: http://localhost:8503 | Log: ~/Library/Logs/LMTStudioPro')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'launchctl thất bại (mã {exc.returncode}). Chạy trong Terminal của tài khoản đang đăng nhập; kiểm tra status và log.')
