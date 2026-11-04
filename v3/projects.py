"""Local project files and immutable render snapshots, never committed to Git."""
from __future__ import annotations
import json
from . import locking as fcntl
import unicodedata
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
    default = (Path(os.getenv('LOCALAPPDATA', Path.home()/'AppData/Local'))/'LMTStudioPro/V3') if os.name=='nt' else Path.home() / ('Library/Application Support/LMTStudioPro/V3' if sys.platform == 'darwin' else '.local/share/lmt-studio-pro/v3')
    path = Path(os.getenv('LMT_V3_HOME', default)).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def atomic(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush(); os.fsync(f.fileno())
    for attempt in range(20):
        try:
            tmp.replace(path);break
        except PermissionError:
            if os.name!='nt' or attempt==19:raise
            time.sleep(.05)  # A Windows reader/antivirus may briefly hold the old file.


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def project_dir(pid):
    if not re.fullmatch(r'[a-f0-9]{32}', pid):
        raise ValueError('Mã dự án không hợp lệ.')
    return home() / pid


def clean_name(name):
    if not isinstance(name,str):raise ValueError('Tên dự án phải là văn bản.')
    name=unicodedata.normalize('NFC',' '.join(name.split()))
    if not name:raise ValueError('Hãy nhập tên riêng cho dự án.')
    if len(name)>120:raise ValueError('Tên dự án tối đa 120 ký tự.')
    return name


def available_name(name, exclude=None, unique_copy=False):
    name=clean_name(name)
    used={clean_name(p['name']).casefold() for p in listing() if p['id']!=exclude}
    if name.casefold() not in used:return name
    if not unique_copy:raise ValueError('Tên dự án đã có. Hãy chọn tên khác để dễ phân biệt.')
    base=name[:100];number=1
    while True:
        candidate=f'{base} (bản sao {number})'
        if candidate.casefold() not in used:return candidate
        number+=1


OUTPUT_DEFAULTS = dict(aspect='16:9', resolution=720, fit='cover', transition='cut',
                       sync_voice=True, original_volume=0, music_volume=0.15,
                       voice_volume=1.0, duck=True, font_size=48, subtitle_mode='words')


def validate_output_defaults(settings):
    result = dict(OUTPUT_DEFAULTS)
    choices = dict(aspect=['9:16','16:9','1:1'], resolution=[720,1080],
                   fit=['contain','cover'], transition=['cut','fade'], subtitle_mode=['words','sentence'])
    for key, options in choices.items():
        value = settings.get(key, result[key])
        if value not in options: raise ValueError('Cấu hình xuất không hợp lệ: '+key)
        result[key] = value
    for key in ('sync_voice','duck'):
        value = settings.get(key, result[key])
        if type(value) is not bool: raise ValueError('Cấu hình xuất không hợp lệ: '+key)
        result[key] = value
    for key, maximum in [('original_volume',1),('music_volume',1),('voice_volume',2),('font_size',64)]:
        value = settings.get(key, result[key])
        minimum = 16 if key == 'font_size' else 0
        if type(value) not in (int,float) or not minimum <= value <= maximum:
            raise ValueError('Cấu hình xuất không hợp lệ: '+key)
        if key == 'font_size' and type(value) is not int: raise ValueError('Cỡ chữ phải là số nguyên.')
        result[key] = value
    return result


def output_defaults():
    path = home()/'output-defaults.json'
    return validate_output_defaults(read(path) if path.exists() else {})


def save_output_defaults(settings):
    atomic(home()/'output-defaults.json', validate_output_defaults(settings))


STORY_DEFAULTS = dict(enabled=True, no_intro=False, remove_background=True, restore_missing=True, keep_attached_objects=True,
                      width=75, x=50, y=100, auto_subtitles=True,
                      asr_model='small', auto_pixabay=True, export_include_assets=True)


def validate_story_defaults(settings):
    result = dict(STORY_DEFAULTS)
    for key, default in STORY_DEFAULTS.items():
        value = settings.get(key, default)
        if type(default) is bool:
            valid = type(value) is bool
        elif key == 'asr_model':
            valid = value in ('small','base','tiny')
        else:
            valid = type(value) is int and (10 if key == 'width' else 0) <= value <= 100
        if not valid:raise ValueError('Cấu hình mục 05 không hợp lệ: '+key)
        result[key] = value
    return result


def story_defaults():
    path = home()/'story-defaults.json'
    return validate_story_defaults(read(path) if path.exists() else {})


def save_story_defaults(settings):
    atomic(home()/'story-defaults.json', validate_story_defaults(settings))


def create(name, unique_copy=False):
    with (home()/'.project-names.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        name=available_name(name,unique_copy=unique_copy)
        pid = uuid4().hex
        folder = project_dir(pid)
        (folder / 'assets').mkdir(parents=True)
        data = dict(id=pid, name=name, scenes=[], voice=None, music=None,
                    captions=None, subtitle_text='', settings=output_defaults(),
                    export_include_assets=story_defaults()['export_include_assets'], updated=time.time())
        atomic(folder/'project.json', data)
    return data


def rename(pid, name):
    with (home()/'.project-names.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        name=available_name(name,exclude=pid)
        project=read(project_dir(pid)/'project.json')
        project['name']=name
        save(project)
    return project


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


def signature_upload(uploaded):
    import hashlib
    return hashlib.sha256(uploaded.getbuffer()).hexdigest()


def upload(folder, file, allowed):
    suffix = Path(file.name).suffix.lower()
    if suffix not in allowed:
        raise ValueError('Định dạng tệp chưa được hỗ trợ.')
    name = uuid4().hex + suffix
    path = Path(folder)/'assets'/name
    file.seek(0)
    with path.open('wb') as target:
        shutil.copyfileobj(file,target,1024*1024)
    if not path.stat().st_size:
        path.unlink()
        raise ValueError('Tệp tải lên đang rỗng.')
    return name


def natural(name):
    return [int(v) if v.isdigit() else v.casefold() for v in re.split(r'(\d+)',name)]


def choose_folder():
    """Native picker runs only in the local Mac app, on an explicit button click."""
    import subprocess
    if os.name == 'nt':
        result = subprocess.run(['powershell.exe','-NoProfile','-STA','-Command',
            "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='LMT Studio V3'; if($d.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Write-Output $d.SelectedPath}"],
            capture_output=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode: raise ValueError('Không mở được hộp chọn thư mục. Hãy nhập đường dẫn.')
        return result.stdout.strip() or None
    if sys.platform != 'darwin':
        raise ValueError('Trên máy này, hãy nhập đường dẫn thư mục vào ô bên dưới.')
    result = subprocess.run(['osascript','-e',
        'POSIX path of (choose folder with prompt "Chọn thư mục lưu dự án LMT")'],
        capture_output=True,text=True)
    if result.returncode:
        if '-128' in result.stderr: return None  # User cancelled the picker.
        raise ValueError('Chưa mở được cửa sổ chọn thư mục. Bạn có thể nhập đường dẫn trực tiếp.')
    return result.stdout.strip() or None


def referenced_assets(project):
    story=project.get('story',{})
    return sorted({scene['file'] for scene in project.get('scenes',[])} |
                  {project[key] for key in ('voice','music','captions','caption_words','voice_track','overlay_image') if project.get(key)} |
                  {story[key] for key in ('image','intro','cutout') if story.get(key)} |
                  set(story.get('backgrounds',[])) |
                  {item['file'] for item in story.get('downloaded',{}).values()})



def export_run(run, destination, include_assets=True):
    """Copy a completed render into a new folder; never overwrite user files."""
    import tempfile
    run=Path(run)
    if not (run/'output.mp4').is_file():raise ValueError('Video chưa hoàn thành để lưu.')
    if not isinstance(destination,str) or not destination.strip():
        raise ValueError('Hãy chọn hoặc nhập thư mục lưu.')
    target=Path(destination.strip()).expanduser()
    if not target.is_absolute():raise ValueError('Hãy nhập đường dẫn đầy đủ, ví dụ ~/Movies/LMT.')
    target.mkdir(parents=True,exist_ok=True)
    target=target.resolve()
    project=read(run/('render-project.json' if (run/'render-project.json').exists() else 'snapshot.json'))
    source=project_dir(project['id'])
    # A metadata rename after rendering should also name the saved bundle correctly.
    project=dict(project,name=read(source/'project.json').get('name',project['name']))
    if target==source or source in target.parents:
        raise ValueError('Chọn thư mục ngoài nơi lưu nội bộ của dự án, ví dụ Movies hoặc ổ đĩa ngoài.')
    name=re.sub(r'[^\w .-]','_',project.get('name','LMT'),flags=re.UNICODE).strip(' .')[:70] or 'LMT'
    stamp=time.strftime('%Y%m%d-%H%M%S')
    temporary=Path(tempfile.mkdtemp(prefix='.lmt-export-',dir=target))
    final=target/(name+'-'+stamp+'-'+uuid4().hex[:8])
    try:
        shutil.copy2(run/'output.mp4',temporary/'video.mp4')
        if (run/'captions.srt').exists():shutil.copy2(run/'captions.srt',temporary/'captions.srt')
        if include_assets:
            (temporary/'assets').mkdir()
            for filename in referenced_assets(project):
                shutil.copy2(asset(source,filename),temporary/'assets'/filename)
            atomic(temporary/'project.json',dict(project,bundle_version=1))
            if project.get('story',{}).get('downloaded'):
                atomic(temporary/'pixabay-downloads.json',project['story']['downloaded'])
        (temporary/'README.txt').write_text(
            'Video thành phẩm: video.mp4\n'+
            ('Mở lại: vào LMT V3, chọn Nhập dự án từ thư mục và chọn thư mục này.\n'
             if include_assets else 'Bản này chỉ có video/phụ đề; dự án gốc vẫn được giữ trong LMT V3.\n'),encoding='utf8')
        temporary.rename(final)
    except Exception:
        shutil.rmtree(temporary,ignore_errors=True)
        raise
    return str(final)


def import_bundle(directory):
    source=Path(directory).expanduser().resolve()
    project=read(source/'project.json')
    if not isinstance(project,dict) or project.get('bundle_version')!=1 or not isinstance(project.get('scenes'),list):
        raise ValueError('Thư mục này không phải bản dự án LMT V3 hoàn chỉnh.')
    names=referenced_assets(project)
    # Validate every source path before creating a project or copying any file.
    paths={name:asset(source,name) for name in names}
    imported=create(project.get('name','Dự án đã nhập'),unique_copy=True)
    target=project_dir(imported['id'])
    try:
        for name,path in paths.items():shutil.copy2(path,target/'assets'/name)
        if project.get('story',{}).get('downloaded'):
            atomic(target/'pixabay-downloads.json',project['story']['downloaded'])
        project=dict(project,id=imported['id'],name=imported['name'])
        project.pop('bundle_version',None)
        save(project)
    except Exception:
        shutil.rmtree(target,ignore_errors=True)
        raise
    return project
