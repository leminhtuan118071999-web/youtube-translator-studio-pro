#!/usr/bin/env python3
"""Local V2 worker bootstrap. Credentials never enter shell commands or Git.

Run on your own computer: python3 v2/start_local_worker.py
Use --configure to replace saved settings. Keep the computer powered on.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import venv
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
VIRTUAL_ENV = ROOT / '.venv-worker'
CONFIG_DIR = Path.home() / ("Library/Application Support/LMTStudioPro" if sys.platform == 'darwin' else '.config/lmt-studio-pro')
CONFIG_PATH = CONFIG_DIR / 'worker.json'
DEFAULT_URL = 'https://pkwvokftldnlemkjpkro.supabase.co'
FIELDS = ('DATABASE_URL','SESSION_ENCRYPTION_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY')


def validate_config(config):
    if not isinstance(config, dict) or any(not isinstance(config.get(k, ''), str) for k in FIELDS):
        raise ValueError('Cấu hình worker chưa hợp lệ. Chạy lại với --configure.')
    dsn = urlsplit(config.get('DATABASE_URL', ''))
    if dsn.scheme not in ('postgres','postgresql') or not dsn.hostname:
        raise ValueError('DATABASE_URL phải là chuỗi kết nối PostgreSQL đầy đủ.')
    if dsn.hostname not in ('localhost','127.0.0.1','::1') and parse_qs(dsn.query).get('sslmode', [''])[0] not in ('require','verify-ca','verify-full'):
        raise ValueError('DATABASE_URL kết nối Supabase cần thêm sslmode=require.')
    try:
        key = base64.b64decode(config.get('SESSION_ENCRYPTION_KEY',''), altchars=b'-_', validate=True)
    except (ValueError, TypeError):
        key = b''
    if len(key) != 32:
        raise ValueError('SESSION_ENCRYPTION_KEY phải là khóa Fernet V1, không tạo khóa mới.')
    url = urlsplit(config.get('SUPABASE_URL', ''))
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('SUPABASE_URL phải là địa chỉ HTTPS của dự án Supabase.')
    return {k: config.get(k, '') for k in FIELDS}


def write_config(path, config):
    config = validate_config(config)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix='.worker-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(config, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_config(path):
    if path.is_symlink():
        raise ValueError('Tệp cấu hình không được là liên kết tượng trưng.')
    try:
        with path.open(encoding='utf-8') as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        raise ValueError('Không đọc được cấu hình. Chạy lại với --configure.') from None
    os.chmod(path, 0o600)
    return validate_config(config)


def configure():
    print('Nhập trên máy của bạn; các giá trị bí mật sẽ không hiện khi gõ.')
    print('Dùng cùng DATABASE_URL và đúng khóa Fernet V1 đã lưu cho API Render.')
    config = {
        'DATABASE_URL': getpass.getpass('DATABASE_URL (Supabase, có sslmode=require): ').strip(),
        'SESSION_ENCRYPTION_KEY': getpass.getpass('SESSION_ENCRYPTION_KEY của V1: ').strip(),
        'SUPABASE_URL': input(f'SUPABASE_URL [{DEFAULT_URL}]: ').strip() or DEFAULT_URL,
        'SUPABASE_SERVICE_ROLE_KEY': getpass.getpass('Storage service-role key (tùy chọn; Enter để bỏ qua): ').strip(),
    }
    write_config(CONFIG_PATH, config)
    print('Đã lưu cấu hình riêng trên máy; không ghi vào repository.')
    return config


def bootstrap():
    if sys.version_info < (3, 12):
        raise ValueError('Cần Python 3.12 trở lên. Cài từ python.org rồi mở lại tệp khởi chạy.')
    python = VIRTUAL_ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Đang tạo môi trường Python riêng cho worker...', flush=True)
        venv.EnvBuilder(with_pip=True).create(VIRTUAL_ENV)
    requirements = ROOT / 'backend/requirements.txt'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = VIRTUAL_ENV / 'requirements.sha256'
    if not stamp.exists() or stamp.read_text() != digest:
        print('Đang cài thư viện; chỉ cài lại khi requirements thay đổi...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        stamp.write_text(digest)
    # Re-exec without command-line credentials; env/settings are loaded below.
    os.execv(str(python), [str(python), str(Path(__file__).resolve()), '--worker', *sys.argv[1:]])


def run_worker(config):
    os.environ.update(config)
    os.chdir(ROOT / 'backend')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app import worker
    from app.settings import get_settings
    get_settings.cache_clear()
    # Check schema/key before starting caffeinate or reporting readiness.
    worker.seal({})
    with worker.connect() as conn:
        conn.execute('select input_revision,request_id from public.lmt_v2_jobs limit 0')
    keep_awake = None
    if sys.platform == 'darwin' and shutil.which('caffeinate'):
        # Keep system idle sleep off while THIS process lives. Display may sleep.
        keep_awake = subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if os.environ.get('LMT_V2_BACKGROUND')=='1':
            print('Worker nền V2 đã kết nối. Không cần mở cửa sổ Terminal.',flush=True)
        else:
            print('Worker đã kết nối. Có thể đóng trình duyệt; giữ cửa sổ Terminal này mở.', flush=True)
        print('Máy phải có mạng và không tắt/ngủ. Trên Mac, giữ nắp máy mở và cắm sạc.', flush=True)
        print('Dừng bằng background_worker.py stop; checkpoint được giữ trong Supabase.'
              if os.environ.get('LMT_V2_BACKGROUND')=='1' else
              'Nhấn Ctrl+C để dừng; checkpoint được giữ trong Supabase.', flush=True)
        worker.main()
    finally:
        if keep_awake:
            keep_awake.terminate()
            keep_awake.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description='Chạy LMT V2 worker miễn phí trên máy cá nhân.')
    parser.add_argument('--configure', action='store_true', help='Nhập lại cấu hình riêng trên máy.')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.worker:
        bootstrap()
    config = configure() if args.configure or not CONFIG_PATH.exists() else read_config(CONFIG_PATH)
    run_worker(config)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nĐã dừng worker.')
    except Exception:
        # Do not print exception bodies: database/provider errors may contain
        # connection identifiers or credentials supplied by the local user.
        print('Chưa chạy được worker. Kiểm tra Python, mạng, DATABASE_URL, khóa V1 và migration V2.')
        print('Nếu cần nhập lại cấu hình: python3 v2/start_local_worker.py --configure')
        sys.exit(1)

