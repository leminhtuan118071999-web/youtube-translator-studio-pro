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
from .render import probe, run_ffmpeg, validate_srt, Cancelled


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


def validate_start(project,destination):
    cfg=project.get('story',{})
    missing=[]
    if cfg.get('enabled'):
        if not project.get('voice'):missing.append('file giọng đọc chính')
        if not cfg.get('backgrounds') and not cfg.get('pixabay_selected'):
            from .pixabay import api_key
            can_choose_theme = cfg.get('auto_theme', False) and cfg.get('image')
            if not cfg.get('auto_pixabay', True) or not (cfg.get('query', 'forest sunlight').strip() or can_choose_theme) or not api_key():
                missing.append('video nền hoặc từ khóa và khóa Pixabay để tự tìm nền')
    elif not project.get('scenes'):missing.append('bật chế độ dựng video nền + giọng đọc và thêm nguyên liệu')
    if not destination.strip():missing.append('nơi lưu kết quả')
    elif not Path(destination.strip()).expanduser().is_absolute():missing.append('đường dẫn nơi lưu đầy đủ')
    if missing:raise ValueError('Chưa thể bắt đầu. Cần bổ sung: '+ '; '.join(missing)+'.')


# Version the cache whenever segmentation changes; never reuse the old u2netp mask.
CUTOUT_VERSION = 'birefnet-attached-details-v3'


def cutout_signature(config):
    return signature(dict(version=CUTOUT_VERSION, **{k:config.get(k) for k in
        ('image','remove_background','restore_missing','keep_attached_objects','keep_boxes')}))


def attached_details(candidate,person):
    """Keep predicted foreground components that touch the person's silhouette."""
    import numpy as np
    from scipy import ndimage
    from PIL import Image,ImageChops
    size=candidate.size
    ratio=min(1,1024/max(size))
    small=(max(1,round(size[0]*ratio)),max(1,round(size[1]*ratio)))
    foreground=np.asarray(candidate.resize(small,Image.Resampling.BILINEAR))>=160
    anchor=np.asarray(person.resize(small,Image.Resampling.BILINEAR))>=224
    # Small gaps at fingers/straps are tolerated; distant foreground stays out.
    anchor=ndimage.binary_dilation(anchor,iterations=max(1,round(max(small)*.005)))
    labels,count=ndimage.label(foreground)
    connected=np.unique(labels[anchor & foreground])
    connected=connected[connected>0]
    keep=np.isin(labels,connected) if count else np.zeros_like(foreground)
    selection=Image.fromarray(keep.astype('uint8')*255).resize(size,Image.Resampling.NEAREST)
    return ImageChops.darker(candidate,selection)


def group_cutout(original,restore_missing=True,keep_attached_objects=True):
    """Union full-frame and overlapping regional masks, preserving source pixels."""
    from PIL import Image, ImageChops
    from rembg import remove, new_session
    session = new_session('birefnet-general', providers=['CPUExecutionProvider'])
    rgb = original.convert('RGB')
    def predict(image,model_session=session):
        mask = remove(image, session=model_session, only_mask=True).convert('L')
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.Resampling.LANCZOS)
        return mask
    alpha = predict(rgb)
    w, h = rgb.size
    # Overlap avoids splitting people at the center; full-frame mask stays intact.
    if w >= h and w >= 600:
        for left, right in ((0, round(w*.65)), (round(w*.35), w)):
            box = (left, 0, right, h)
            regional = Image.new('L', rgb.size)
            regional.paste(predict(rgb.crop(box)), (left, 0))
            alpha = ImageChops.lighter(alpha, regional)
    elif h > w and h >= 600:
        for top, bottom in ((0, round(h*.65)), (round(h*.35), h)):
            box = (0, top, w, bottom)
            regional = Image.new('L', rgb.size)
            regional.paste(predict(rgb.crop(box)), (0, top))
            alpha = ImageChops.lighter(alpha, regional)
    if restore_missing or keep_attached_objects:
        # Independent person model can recover limbs/interior regions missed in
        # every BiRefNet view. Only its high-confidence pixels may add opacity;
        # weak background predictions cannot reintroduce a background rectangle.
        human_session = new_session('u2net_human_seg', providers=['CPUExecutionProvider'])
        human = predict(rgb,human_session)
        recovery = human.point([0 if value <= 224 else round((value-224)*255/31)
                                for value in range(256)])
        if restore_missing:alpha = ImageChops.lighter(alpha,recovery)
        if keep_attached_objects:
            bbox=recovery.getbbox()
            if bbox:
                l,t,r,b=bbox
                margin_x=max(8,round((r-l)*.3));margin_y=max(8,round((b-t)*.15))
                box=(max(0,l-margin_x),max(0,t-margin_y),min(w,r+margin_x),min(h,b+margin_y))
                # A full-image crop adds no new evidence; existing multiview
                # masks already cover it. Focus the extra pass on the person.
                if (box[2]-box[0])*(box[3]-box[1]) < w*h*.9:
                    details=predict(rgb.crop(box))
                    attached=attached_details(details,recovery.crop(box))
                    regional=Image.new('L',rgb.size);regional.paste(attached,box[:2])
                    alpha=ImageChops.lighter(alpha,regional)
    # Respect existing transparency. Do not synthesize hidden body parts or pixels.
    alpha = ImageChops.multiply(alpha, original.getchannel('A'))
    result = original.copy()
    result.putalpha(alpha)
    return result


def cutout(folder,config):
    from PIL import Image, ImageOps
    source=asset(folder,config['image'])
    with Image.open(source) as opened:
        if opened.width*opened.height>40000000:raise ValueError('Ảnh nhân vật vượt 40 triệu pixel.')
        original=ImageOps.exif_transpose(opened).convert('RGBA')
    if config.get('remove_background',True):
        os.environ.setdefault('U2NET_HOME',str(home()/'models'/'rembg'))
        os.environ.setdefault('OMP_NUM_THREADS','2')
        result=group_cutout(original,restore_missing=config.get('restore_missing',True),
                            keep_attached_objects=config.get('keep_attached_objects',True))
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
    png = None
    if cfg.get('image'):
        update(2, 'Bước 1/6 · Chuẩn bị ảnh nhân vật')
        sig = cutout_signature(cfg)
        png = cached('cutout', sig)
        if not png:
            png = cutout(folder, cfg)
            remember('cutout', sig, png)
        current = read(folder/'project.json')
        current.setdefault('story', {})['cutout'] = png
        save(current)
    else:
        update(2, 'Bước 1/6 · Dựng video nền và giọng đọc')
    update(10,'Bước 2/6 · Chuẩn bị video nền')
    from .pixabay import download,select_for_project
    selected=cfg.get('pixabay_selected',[])
    if not cfg.get('backgrounds') and cfg.get('auto_pixabay',True):
        update(10,'Bước 2/6 · Đang chọn 15 video Pixabay mới, tránh trùng phiên trước')
        records=read(folder/'pixabay-downloads.json') if (folder/'pixabay-downloads.json').exists() else {}
        if records and not (folder/'pixabay-selection.json').exists():
            # Preserve older projects that already downloaded their backgrounds.
            cfg['backgrounds']=[r['file'] for r in records.values()]
            selected=[]
        else:
            query=cfg.get('query','forest sunlight')
            if not selected and not (folder/'pixabay-selection.json').exists():
                from .thumbnail_theme import resolve_query
                query=resolve_query(folder,cfg,cancel,lambda stage:update(10,stage))
            effective['story']['resolved_query']=query
            selected=select_for_project(folder,query,selected,cancel,update=lambda stage:update(10,stage))
    downloaded=download(folder,selected,cancel,lambda p,s:update(10+round(10*p),s))
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
    update(22,'Bước 3/6 · Nối giọng mở đầu và giọng chính')
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
    def intro_offset():
        intro = cfg.get('intro')
        if not intro:
            return 0
        # Measure decoded samples so MP3 encoder padding cannot shift the subtitles.
        intro_pcm = run/'caption-intro.wav'
        run_ffmpeg(['-i', str(asset(folder, intro)), '-vn', '-ar', '48000',
                    '-ac', '2', '-c:a', 'pcm_s16le', str(intro_pcm)], run, cancel)
        duration = probe(intro_pcm)['duration']
        intro_pcm.unlink()
        return duration

    if cfg.get('main_srt') and cfg.get('main_srt_voice') == project['voice']:
        key = signature(['main-only-v1', joined, cfg['main_srt']])
        srtfile = cached('provided-srt', key)
        if not srtfile:
            update(25, 'Bước 4/6 · Dùng phụ đề có sẵn của giọng chính')
            main_duration = probe(asset(folder, project['voice']))['duration']
            source = asset(folder, cfg['main_srt']).read_text(encoding='utf-8-sig')
            main_cues = validate_srt(source, main_duration, offset=intro_offset())
            srtfile = uuid4().hex+'.srt'
            duration = probe(asset(folder, joined))['duration']
            (folder/'assets'/srtfile).write_text(validate_srt(main_cues, duration), encoding='utf-8')
            remember('provided-srt', key, srtfile)
        effective.update(captions=srtfile, caption_words=None, captions_origin='provided')
    elif cfg.get('auto_subtitles', True):
        from .speech import transcribe, to_srt
        model = cfg.get('asr_model', 'small')
        key = signature(['main-only-v1', joined, model])
        wordfile = cached('words', key)
        srtfile = cached('srt', key)
        if not wordfile or not srtfile:
            offset = intro_offset()
            subrun = run/'speech-main'
            subrun.mkdir(exist_ok=True)
            atomic(subrun/'snapshot.json', dict(project, asr_model=model))
            transcribe(subrun, report=lambda p,s:update(25+round(25*p/100), 'Bước 4/6 · '+s))
            data = read(subrun/'words.json')
            words = [dict(word, start=round(word['start']+offset, 3), end=round(word['end']+offset, 3))
                     for word in data['words']]
            wordfile = uuid4().hex+'.json'
            srtfile = uuid4().hex+'.srt'
            atomic(folder/'assets'/wordfile, dict(words=words, source_voice=joined, language=data['language']))
            (folder/'assets'/srtfile).write_text(to_srt(words), encoding='utf-8')
            remember('words', key, wordfile)
            remember('srt', key, srtfile)
        effective.update(captions=srtfile, caption_words=wordfile, captions_origin='asr')
    else:
        # Manual captions in this mode must cover the entire intro+main timeline.
        if project.get('captions_origin') in ('asr', 'provided'):
            effective.update(captions=None,caption_words=None,subtitle_text='')
    if png:
        effective['story']['cutout'] = png
    else:
        effective['story'].pop('cutout', None)
    atomic(run/'render-project.json',effective)
    update(50, 'Đã chuẩn bị xong nguyên liệu dựng video')


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
    sig=cutout_signature(cfg)
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

