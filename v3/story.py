"""Prepare a layered storytelling project locally, before FFmpeg rendering."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4
from .projects import home, project_dir, asset, read, atomic, save
from .render import probe, run_ffmpeg, Cancelled


def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def voice_duration(project,folder):
    total=0
    for name in (project.get('story',{}).get('intro'),project.get('voice')):
        if name:
            info=probe(asset(folder,name))
            if not info['audio'] or info['duration']<=0:raise ValueError('File giọng đọc phải có âm thanh hợp lệ.')
            total+=info['duration']
    if not project.get('voice'):raise ValueError('Hãy thêm file giọng đọc chính.')
    if not 0<total<=14400:raise ValueError('Tổng giọng mở đầu và giọng chính phải dưới 4 giờ.')
    return total


def cutout(folder,config):
    from PIL import Image, ImageOps
    source=asset(folder,config['image'])
    with Image.open(source) as opened:
        if opened.width*opened.height>40000000:raise ValueError('Ảnh nhân vật vượt 40 triệu pixel.')
        original=ImageOps.exif_transpose(opened).convert('RGBA')
    if config.get('remove_background',True):
        os.environ.setdefault('U2NET_HOME',str(home()/'models'/'rembg'))
        os.environ.setdefault('OMP_NUM_THREADS','2')
        from rembg import remove,new_session
        result=remove(original,session=new_session('u2netp',providers=['CPUExecutionProvider']))
    else:result=original.copy()
    # Optional keep boxes restore original details, without regenerating the image.
    for box in config.get('keep_boxes',[]):
        if len(box)!=4 or not all(isinstance(v,(int,float)) and 0<=v<=100 for v in box):raise ValueError('Vùng giữ thêm không hợp lệ.')
        l,t,r,b=box
        if l>=r or t>=b:raise ValueError('Vùng giữ thêm cần trái < phải và trên < dưới.')
        bounds=(round(original.width*l/100),round(original.height*t/100),round(original.width*r/100),round(original.height*b/100))
        result.paste(original.crop(bounds),bounds[:2])
    bbox=result.getchannel('A').getbbox()
    if bbox is None:raise ValueError('Ảnh tách nền bị rỗng. Hãy dùng PNG đã tách nền hoặc chỉnh vùng giữ thêm.')
    result=result.crop(bbox)
    name=uuid4().hex+'.png';result.save(Path(folder)/'assets'/name)
    return name


def prepare(run):
    run=Path(run);project=read(run/'snapshot.json');folder=project_dir(project['id']);cfg=project['story'];cancel=run/'cancel'
    effective=copy.deepcopy(project)
    def update(progress,stage):
        if cancel.exists():raise Cancelled()
        atomic(run/'status.json',dict(state='running',task='render',progress=progress,stage=stage,updated=time.time()))
    voice_duration(project,folder)
    cache_path=folder/'story-cache.json';cache=read(cache_path) if cache_path.exists() else {}
    def cached(key,sig):
        item=cache.get(key,{})
        if item.get('signature')!=sig:return None
        try:asset(folder,item['file']);return item['file']
        except (ValueError,KeyError):return None
    def remember(key,sig,name):
        cache[key]=dict(signature=sig,file=name);atomic(cache_path,cache)
    update(2,'Đang tách nền và giữ nhân vật; lần đầu cần tải model')
    sig=signature({k:cfg.get(k) for k in ('image','remove_background','keep_boxes')})
    png=cached('cutout',sig)
    if not png:png=cutout(folder,cfg);remember('cutout',sig,png)
    # Make the resulting cutout visible in the project even if a later stage fails.
    current=read(folder/'project.json');current.setdefault('story',{})['cutout']=png;save(current)
    update(10,'Đang chuẩn bị video nền')
    from .pixabay import download
    downloaded=download(folder,cfg.get('pixabay_selected',[]),cancel,lambda p,s:update(10+round(10*p),s))
    effective['story']['downloaded']=read(folder/'pixabay-downloads.json') if (folder/'pixabay-downloads.json').exists() else {}
    current=read(folder/'project.json');current['story']['downloaded']=effective['story']['downloaded'];save(current)
    backgrounds=list(dict.fromkeys(cfg.get('backgrounds',[])+downloaded))
    if not backgrounds:raise ValueError('Hãy tải video nền lên hoặc chọn video Pixabay.')
    if len(backgrounds)>300:raise ValueError('Tối đa 300 video nền.')
    scenes=[]
    for name in backgrounds:
        media=probe(asset(folder,name))
        if not media['video'] or media['duration']<=0:raise ValueError('Nền phải là video có thời lượng hợp lệ.')
        scenes.append(dict(id=uuid4().hex,file=name,name=name,duration=min(3600,media['duration'])))
    update(22,'Đang nối giọng mở đầu với giọng đọc chính')
    voices=[v for v in (cfg.get('intro'),project['voice']) if v]
    sig=signature(voices);joined=cached('voice',sig)
    if not joined:
        joined=uuid4().hex+'.wav'
        args=[];filters=[]
        for i,name in enumerate(voices):
            args+=['-i',str(asset(folder,name))]
            filters.append(f'[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[v{i}]')
        filters.append(''.join(f'[v{i}]' for i in range(len(voices)))+f'concat=n={len(voices)}:v=0:a=1[out]')
        run_ffmpeg(args+['-filter_complex',';'.join(filters),'-map','[out]','-c:a','pcm_s16le',str(folder/'assets'/joined)],run,cancel)
        remember('voice',sig,joined)
    effective.update(voice_track=joined,scenes=scenes,overlay_image=png)
    effective['settings'].update(sync_voice=True,original_volume=0,fit='cover')
    if cfg.get('auto_subtitles',True):
        from .speech import transcribe,to_srt
        key=signature([voices,joined,cfg.get('asr_model','small')]);wordfile=cached('words',key)
        srtfile=cached('srt',key)
        if not wordfile or not srtfile:
            words=[];offset=0;languages=[]
            for i,name in enumerate(voices):
                subrun=run/('speech-'+str(i));subrun.mkdir(exist_ok=True)
                atomic(subrun/'snapshot.json',dict(project,voice=name,asr_model=cfg.get('asr_model','small')))
                transcribe(subrun,report=lambda p,s:update(25+round(25*(i+p/100)/len(voices)),s))
                data=read(subrun/'words.json');languages.append(data['language'])
                words.extend(dict(w,start=round(w['start']+offset,3),end=round(w['end']+offset,3)) for w in data['words'])
                offset+=probe(asset(folder,name))['duration']
            wordfile=uuid4().hex+'.json';srtfile=uuid4().hex+'.srt'
            atomic(folder/'assets'/wordfile,dict(words=words,source_voice=joined,language='+'.join(dict.fromkeys(languages))))
            (folder/'assets'/srtfile).write_text(to_srt(words),encoding='utf8')
            remember('words',key,wordfile);remember('srt',key,srtfile)
        effective.update(captions=srtfile,caption_words=wordfile,captions_origin='asr')
    else:
        # Manual captions in this mode must cover the entire intro+main timeline.
        if project.get('captions_origin')=='asr':
            effective.update(captions=None,caption_words=None,subtitle_text='')
    effective['story']['cutout']=png
    atomic(run/'render-project.json',effective)
    update(50,'Đã chuẩn bị xong ảnh, giọng đọc và video nền')


def layout_preview(project,folder):
    import io
    import subprocess
    from PIL import Image, ImageOps
    cfg=project['story'];backgrounds=cfg.get('backgrounds',[])+[r['file'] for r in cfg.get('downloaded',{}).values()]
    if not backgrounds:raise ValueError('Thêm video nền trên máy hoặc dựng một lần để tải video Pixabay trước khi xem bố cục.')
    info=project['settings'];short=480
    width,height={'9:16':(short,round(short*16/9)),'16:9':(round(short*16/9),short),'1:1':(short,short)}[info['aspect']]
    command=['ffmpeg','-v','error','-i',str(asset(folder,backgrounds[0])),'-vf',f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}',
             '-frames:v','1','-threads','1','-f','image2pipe','-vcodec','png','pipe:1']
    result=subprocess.run(command,capture_output=True,timeout=30)
    if result.returncode:raise ValueError('Chưa đọc được video nền để xem trước.')
    with Image.open(io.BytesIO(result.stdout)) as image:canvas=image.convert('RGBA')
    with Image.open(asset(folder,cfg['cutout'])) as image:character=image.convert('RGBA')
    character.thumbnail((round(width*cfg.get('width',75)/100),round(height*.95)),Image.Resampling.LANCZOS)
    x=round((width-character.width)*cfg.get('x',50)/100);y=round((height-character.height)*cfg.get('y',100)/100)
    canvas.alpha_composite(character,(x,y))
    out=io.BytesIO();canvas.convert('RGB').save(out,format='PNG');return out.getvalue()


def preview_cutout(run):
    run=Path(run);project=read(run/'snapshot.json');folder=project_dir(project['id'])
    cfg=project['story'];cache_path=folder/'story-cache.json';cache=read(cache_path) if cache_path.exists() else {}
    sig=signature({k:cfg.get(k) for k in ('image','remove_background','keep_boxes')})
    atomic(run/'status.json',dict(state='running',task='cutout',progress=5,stage='Đang tách nền ảnh; lần đầu tải model',updated=time.time()))
    image=cutout(folder,cfg)
    cache['cutout']=dict(signature=sig,file=image);atomic(cache_path,cache)
    current=read(folder/'project.json');current.setdefault('story',{})['cutout']=image;save(current)
    atomic(run/'cutout-result.json',dict(image=image))


if __name__=='__main__':
    try:
        if len(sys.argv)>2 and sys.argv[2]=='cutout':preview_cutout(sys.argv[1])
        else:prepare(sys.argv[1])
    except Exception as exc:
        atomic(Path(sys.argv[1])/'prepare-error.json',{'error':str(exc)[-2000:]});raise
