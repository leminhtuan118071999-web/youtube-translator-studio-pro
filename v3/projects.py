"""Local project files and immutable render snapshots, never committed to Git."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from uuid import uuid4

MEDIA = {'.mp4','.mov','.mkv','.webm','.jpg','.jpeg','.png','.webp'}
AUDIO = {'.mp3','.wav','.m4a','.aac','.flac','.ogg'}
IMAGES = {'.jpg','.jpeg','.png','.webp'}


def home():
    default = Path.home() / ('Library/Application Support/LMTStudioPro/V3' if sys.platform == 'darwin' else '.local/share/lmt-studio-pro/v3')
    path = Path(os.getenv('LMT_V3_HOME', default)).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def atomic(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush(); os.fsync(f.fileno())
    tmp.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def project_dir(pid):
    if not re.fullmatch(r'[a-f0-9]{32}', pid):
        raise ValueError('Mã dự án không hợp lệ.')
    return home() / pid


def create(name):
    pid = uuid4().hex
    folder = project_dir(pid)
    (folder / 'assets').mkdir(parents=True)
    data = dict(id=pid, name=name.strip()[:120] or 'Video mới', scenes=[], voice=None, music=None,
                captions=None, subtitle_text='', settings=dict(aspect='9:16', resolution=1080,
                fit='contain', transition='cut', sync_voice=True, original_volume=0,
                music_volume=0.15, voice_volume=1.0, duck=True, font_size=48), updated=time.time())
    atomic(folder/'project.json', data)
    return data


def listing():
    rows = []
    for path in home().glob('*/project.json'):
        try: rows.append(read(path))
        except (ValueError,OSError): continue
    return sorted(rows, key=lambda x:x.get('updated',0), reverse=True)


def save(data):
    data = dict(data, updated=time.time())
    atomic(project_dir(data['id'])/'project.json', data)


def asset(folder, name):
    if not isinstance(name,str) or Path(name).name != name or name in ('','.','..'):
        raise ValueError('Đường dẫn nguyên liệu không hợp lệ.')
    path = (Path(folder)/'assets'/name).resolve()
    if path.parent != (Path(folder)/'assets').resolve() or not path.is_file():
        raise ValueError('Không tìm thấy nguyên liệu trong dự án.')
    return path


def upload(folder, file, allowed):
    suffix = Path(file.name).suffix.lower()
    if suffix not in allowed:
        raise ValueError('Định dạng tệp chưa được hỗ trợ.')
    name = uuid4().hex + suffix
    path = Path(folder)/'assets'/name
    with path.open('wb') as target:
        shutil.copyfileobj(file,target,1024*1024)
    if not path.stat().st_size:
        path.unlink()
        raise ValueError('Tệp tải lên đang rỗng.')
    return name


def natural(name):
    return [int(v) if v.isdigit() else v.casefold() for v in re.split(r'(\d+)',name)]
