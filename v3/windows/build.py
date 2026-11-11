"""Build on Windows only. No user data or credentials enter the installer."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import os
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
STAGE=Path(os.getenv('RUNNER_TEMP',tempfile.gettempdir()))/'lmt-v3'


def build():
    if os.name!='nt':raise SystemExit('Build on Windows x64.')
    if STAGE.exists():shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    base=Path(sys.base_prefix);runtime=STAGE/'runtime';runtime.mkdir()
    for name in ('DLLs','Lib'):
        shutil.copytree(base/name,runtime/name,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo','ensurepip'))
    for pattern in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime*.dll','LICENSE.txt'):
        for file in base.glob(pattern):shutil.copy2(file,runtime/file.name)
    target=runtime/'Lib'/'site-packages'
    subprocess.run([sys.executable,'-m','pip','install','--no-compile','--target',str(target),'-r',str(ROOT/'v3'/'requirements.txt')],check=True)
    for directory in sorted(target.rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if directory.is_dir() and directory.name in ('tests','__pycache__','.agents','.claude'):shutil.rmtree(directory)
    shutil.copytree(ROOT/'v3',STAGE/'v3',ignore=shutil.ignore_patterns('.venv*','__pycache__','*.pyc','windows','tests','.DS_Store'))
    # Include focused portability tests for the staged runtime check.
    (STAGE/'v3'/'tests').mkdir()
    for name in ('test_windows_portability.py','test_recovery.py','test_cutout.py','test_story_defaults.py','test_output_defaults.py','test_thumbnail_theme.py'):
        shutil.copy2(ROOT/'v3'/'tests'/name,STAGE/'v3'/'tests'/name)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
                    '--name','LMTStudioV3','--distpath',str(STAGE),'--workpath',str(ROOT/'build'/'pyinstaller'),
                    '--specpath',str(ROOT/'build'),str(ROOT/'v3'/'windows'/'launcher.py')],check=True)
    shutil.copy2(ROOT/'v3'/'windows'/'README.md',STAGE/'README-Windows.md')
    build_info=dict(version='3.3.0',
                    source_commit=os.getenv('GITHUB_HEAD_SHA') or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    built_at=datetime.now(timezone.utc).isoformat())
    manifest=json.dumps(build_info,ensure_ascii=False,indent=2)+'\n'
    (STAGE/'build-info.json').write_text(manifest,encoding='utf8')
    output=ROOT/'dist'/'windows';output.mkdir(parents=True,exist_ok=True)
    (output/'build-info.json').write_text(manifest,encoding='utf8')
    compiler=Path(os.environ.get('ISCC',r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'))
    if not compiler.exists():raise SystemExit('Install Inno Setup 6 to build the Setup.exe.')
    subprocess.run([str(compiler),'/Qp','/DPayloadDir='+str(STAGE),str(ROOT/'v3'/'windows'/'installer.iss')],check=True,cwd=ROOT)
    for file in (ROOT/'dist'/'windows').glob('*.exe'):
        file.with_suffix('.exe.sha256').write_text(hashlib.file_digest(file.open('rb'),'sha256').hexdigest()+'  '+file.name+'\n')


if __name__=='__main__':build()
