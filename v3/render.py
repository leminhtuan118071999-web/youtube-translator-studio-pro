"""Real FFmpeg renderer: local assets, normalized scenes and a narration-led mix."""
from __future__ import annotations
import json
from functools import lru_cache
import math
from pathlib import Path
import re
import os
import queue
import threading
import shutil
import subprocess
import time
from .projects import asset, IMAGES, STORY_DEFAULTS, atomic, read

FPS = 30
EXPORT_STALL_SECONDS = 180
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class Cancelled(Exception): pass


def probe(path):
    path=Path(path).resolve();stat=path.stat()
    return dict(_probe(str(path),stat.st_mtime_ns,stat.st_size))


@lru_cache(maxsize=2048)
def _probe(path, modified, size):
    p = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(path)], capture_output=True, text=True, timeout=40, creationflags=NO_WINDOW)
    if p.returncode:
        raise ValueError('Không đọc được tệp media: '+Path(path).name)
    data = json.loads(p.stdout)
    streams = data.get('streams',[])
    durations = [float(s.get('duration') or 0) for s in [data.get('format',{}),*streams]]
    duration = max(durations, default=0)
    if not math.isfinite(duration) or duration > 14400:
        raise ValueError('Thời lượng media không hợp lệ hoặc vượt 4 giờ.')
    visual=next((s for s in streams if s.get('codec_type')=='video'),{})
    width, height = int(visual.get('width', 0)), int(visual.get('height', 0))
    rotation = next((item['rotation'] for item in visual.get('side_data_list', []) if 'rotation' in item),
                    visual.get('tags', {}).get('rotate', 0))
    try:
        if float(rotation) % 180 == 90:
            width, height = height, width
    except (TypeError, ValueError):
        pass
    return dict(width=width,height=height,
                duration=duration, video=any(s.get('codec_type')=='video' for s in streams),
                audio=any(s.get('codec_type')=='audio' for s in streams))


def plan(project, folder):
    scenes = project.get('scenes',[])
    if not 1 <= len(scenes) <= 300:
        raise ValueError('Cần từ 1 đến 300 cảnh.')
    settings = project['settings']
    if settings['aspect'] not in ('9:16','16:9','1:1') or settings['resolution'] not in (720,1080):
        raise ValueError('Khung hình hoặc độ phân giải không hợp lệ.')
    if settings['fit'] not in ('contain','cover') or settings['transition'] not in ('cut','fade'):
        raise ValueError('Cách căn hình hoặc chuyển cảnh không hợp lệ.')
    for key in ('music_volume','voice_volume','original_volume'):
        if not isinstance(settings[key],(int,float)) or not 0 <= settings[key] <= 2:
            raise ValueError('Âm lượng không hợp lệ.')
    if not 16 <= settings.get('font_size',32) <= 64:
        raise ValueError('Cỡ chữ phải từ 16 đến 64.')
    weights=[]
    for scene in scenes:
        media=probe(asset(folder,scene['file']))
        if not media['video']: raise ValueError('Cảnh phải là video hoặc ảnh.')
        duration=float(scene['duration'])
        if not math.isfinite(duration) or not 0.1 <= duration <= 3600:
            raise ValueError('Thời lượng mỗi cảnh phải từ 0,1 đến 3600 giây.')
        weights.append(duration)
    voice = (project.get('voice_track') if project.get('story',{}).get('enabled') else None) or project.get('voice')
    target=sum(weights)
    if voice:
        audio=probe(asset(folder,voice))
        if not audio['audio'] or audio['duration'] <= 0:
            raise ValueError('File giọng đọc phải có âm thanh hợp lệ.')
        if settings['sync_voice']: target=audio['duration']
        elif audio['duration'] > target + 0.1:
            raise ValueError('Giọng đọc dài hơn timeline. Bật tự khớp thời lượng để tránh cắt lời.')
    if project.get('music') and not probe(asset(folder,project['music']))['audio']:
        raise ValueError('File nhạc nền không có âm thanh.')
    if not 0 < target <= 14400 or round(target*FPS) < len(scenes):
        raise ValueError('Timeline quá ngắn hoặc vượt 4 giờ.')
    if project.get('story',{}).get('enabled'):
        remaining=max(1,round(target*FPS));frames=[]
        for weight in weights:
            count=min(remaining,max(1,round(weight*FPS)));frames.append(count);remaining-=count
            if not remaining:break
        return [count/FPS for count in frames]
    # Distribute integer frames, preserving exact total duration without drift.
    total_frames=round(target*FPS)
    exact=[w/sum(weights)*(total_frames-len(scenes)) for w in weights]
    frames=[1+math.floor(v) for v in exact]
    for i in sorted(range(len(frames)),key=lambda i:exact[i]%1,reverse=True)[:total_frames-sum(frames)]:
        frames[i]+=1
    return [f/FPS for f in frames]


def timestamp(seconds):
    ms=round(seconds*1000); seconds,ms=divmod(ms,1000); minutes,seconds=divmod(seconds,60); hours,minutes=divmod(minutes,60)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def estimated_srt(text,duration):
    # Estimated subtitles are explicitly labelled in the UI, never speech alignment.
    chunks=[]
    for sentence in re.split(r'(?<=[.!?。！？])\s+|\n+',text.strip()):
        words=sentence.split(); line=''
        for word in words:
            if line and len(line)+len(word)+1>78:
                chunks.append(line); line=''
            line=(line+' '+word).strip()
        if line: chunks.append(line)
    weight=sum(max(1,len(c)) for c in chunks)
    out=[]; cursor=0
    for i,chunk in enumerate(chunks):
        end=duration if i==len(chunks)-1 else cursor+duration*max(1,len(chunk))/weight
        if end-cursor < .001: continue
        out.append(f'{len(out)+1}\n{timestamp(cursor)} --> {timestamp(end)}\n{chunk}\n')
        cursor=end
    return '\n'.join(out)


def validate_srt(text,duration, *, offset=0):
    cues=re.findall(r'(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*\n([^\n]+(?:\n(?!\s*\n)[^\n]+)*)',text.strip())
    if not cues: raise ValueError('Phụ đề SRT chưa có mốc thời gian hợp lệ.')
    def secs(t):
        h,m,s,ms=map(int,re.split('[:,.]',t))
        if m>=60 or s>=60: raise ValueError('Mốc thời gian SRT không hợp lệ.')
        return h*3600+m*60+s+ms/1000
    previous=0; out=[]
    for start,end,body in cues:
        a,b=secs(start),secs(end)
        if a<previous or b<=a or b>duration+0.15:
            raise ValueError('Mốc SRT bị chồng lấn hoặc vượt thời lượng video.')
        # Escape ASS override sequences while retaining plain Unicode text.
        body=re.sub(r'<[^>]*>','',body).replace('{','(').replace('}',')')
        out.append(f'{len(out)+1}\n{timestamp(a+offset)} --> {timestamp(b+offset)}\n{body}\n');previous=b
    return '\n'.join(out)


def run_ffmpeg(args, folder, cancel, progress=None, duration=1, *, watch_output=None):
    if cancel.exists(): raise Cancelled()
    # Input decoder threads are scoped per input; encoder -threads does not
    # constrain them. Avoid automatic decoder pools on multi-source graphs.
    args=list(args)
    for index in reversed([i for i,value in enumerate(args) if value=='-i']):
        args[index:index]=['-threads','1']
    base=['ffmpeg','-hide_banner','-loglevel','info','-nostdin','-y','-filter_threads','1','-filter_complex_threads','1']
    with (folder/'ffmpeg-commands.jsonl').open('a',encoding='utf8') as commands:
        commands.write(json.dumps(dict(started=time.time(),args=base+args,output=str(watch_output or '')),ensure_ascii=False)+'\n')
    with (folder/'ffmpeg.log').open('a') as log:
        log.write('\n--- FFmpeg output: '+str(watch_output or args[-1:] )+' ---\n');log.flush()
        process=subprocess.Popen(base+args+['-progress','pipe:1','-nostats'],stdout=subprocess.PIPE,stderr=log,text=True,cwd=folder,creationflags=NO_WINDOW)
        messages=queue.Queue()
        def read_progress():
            for line in process.stdout: messages.put(line.strip())
        reader=threading.Thread(target=read_progress,daemon=True);reader.start()
        last_activity = time.monotonic()
        next_file_check = last_activity
        last_position = 0.0
        last_write = None
        try:
            while process.poll() is None:
                if cancel.exists(): raise Cancelled()
                try: line=messages.get(timeout=.2)
                except queue.Empty: line=''
                if (progress or watch_output is not None) and line.startswith('out_time_us='):
                    try: position = float(line.partition('=')[2]) / 1e6
                    except ValueError: position = 0.0
                    if position > last_position:
                        last_position = position
                        last_activity = time.monotonic()
                        if progress:
                            progress(min(1, position / duration))
                if watch_output is not None and time.monotonic() >= next_file_check:
                    now = time.monotonic()
                    next_file_check = now + 1
                    try:
                        stat = watch_output.stat()
                        write = (stat.st_size, stat.st_mtime_ns)
                    except FileNotFoundError:
                        write = None
                    if write != last_write:
                        last_write = write
                        last_activity = now
                    if now - last_activity >= EXPORT_STALL_SECONDS and process.poll() is None:
                        raise RuntimeError(f'FFmpeg đã dừng tiến độ và không ghi thêm dữ liệu vào {watch_output.name} trong 3 phút. '
                                           'Dự án đã lưu. Bạn có thể dựng lại.')
            if process.returncode:
                tail=(folder/'ffmpeg.log').read_text(errors='replace')[-2500:]
                raise RuntimeError('FFmpeg chưa dựng được video. Chi tiết: '+tail)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill();process.wait()
            reader.join(timeout=3)
            process.stdout.close()
    if cancel.exists(): raise Cancelled()


def cached_ffmpeg(args, folder, cancel, *, inputs, watch_output=None):
    """Reuse only completed intermediates with matching commands and input files."""
    if cancel.exists():raise Cancelled()
    output=folder/args[-1]
    marker=output.with_name(output.name+'.cache.json')
    sources=[]
    for path in inputs:
        path=Path(path).resolve()
        stat=path.stat()
        sources.append([str(path),stat.st_size,stat.st_mtime_ns])
    signature=dict(version=1,args=args,inputs=sources)
    try:
        cached=read(marker)
        stat=output.stat()
        if (cached['signature']==signature and
                cached['output']==[stat.st_size,stat.st_mtime_ns] and stat.st_size>0):
            return True
    except (OSError,ValueError,KeyError,TypeError):
        pass
    marker.unlink(missing_ok=True)
    run_ffmpeg(args,folder,cancel,watch_output=watch_output)
    media=probe(output)
    if media['duration']<=0 or not (media['video'] or media['audio']):
        raise ValueError('Tệp trung gian chưa hoàn chỉnh: '+output.name)
    stat=output.stat()
    atomic(marker,dict(signature=signature,output=[stat.st_size,stat.st_mtime_ns]))
    return False


def portrait_blur_filter(width, height, tail=''):
    # Blur at lower resolution, then expand the background behind the sharp clip.
    small_width, small_height = max(2, width//8*2), max(2, height//8*2)
    return (
        f'[0:v]split[blur_src][sharp_src];'
        f'[blur_src]scale={small_width}:{small_height}:force_original_aspect_ratio=increase:force_divisible_by=2,'
        f'crop={small_width}:{small_height},gblur=sigma=12,scale={width}:{height},setsar=1[blur];'
        f'[sharp_src]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[sharp];'
        f'[blur][sharp]overlay=(W-w)/2:(H-h)/2{tail}[framed]'
    )


def draw_subscribe_sticker(path, width, height):
    from PIL import Image, ImageDraw, ImageFont

    unit = min(width * .46, height * .55) / 320

    def scaled(*coords):
        return tuple(round(value * unit) for value in coords)

    badge = Image.new('RGBA', scaled(320, 84))
    draw = ImageDraw.Draw(badge)
    radius = round(38 * unit)
    draw.rounded_rectangle(scaled(2, 5, 317, 82), radius=radius, fill='#571021')
    draw.rounded_rectangle(scaled(2, 1, 317, 76), radius=radius,
                           fill='#dd1735', outline='#ff8193', width=max(1, round(2 * unit)))
    draw.rounded_rectangle(scaled(18, 15, 68, 62), radius=round(16 * unit), fill='#fff6f7')
    draw.polygon([scaled(37, 26), scaled(37, 51), scaled(55, 38)], fill='#dd1735')
    try:
        font = ImageFont.load_default(size=round(33 * unit))
    except TypeError:  # Pillow versions before scalable default fonts.
        font = ImageFont.load_default()
    draw.text(scaled(190, 38), 'SUBSCRIBE', fill='white', font=font,
              stroke_width=max(1, round(unit)), anchor='mm')
    badge.save(path)
    return badge.width


def prepare_subscribe_clip(folder, sticker, intro_duration, move_duration, corner_scale, cancel):
    """Bake scaling into a finite, constant-size alpha clip.

    Changing scale dimensions inside the final overlay graph can trigger filter
    reconfiguration. Keep that graph's geometry fixed throughout the export.
    """
    import tempfile
    from PIL import Image
    frames=math.ceil((intro_duration+move_duration)*FPS)+2
    with Image.open(sticker) as opened:badge=opened.convert('RGBA')
    with tempfile.TemporaryDirectory(prefix='subscribe-frames-',dir=folder) as temporary:
        sequence=Path(temporary)
        for index in range(frames):
            if cancel.exists():raise Cancelled()
            move=min(1,max(0,(index/FPS-intro_duration)/move_duration))
            scale=1-(1-corner_scale)*move
            size=(max(2,2*round(badge.width*scale/2)),max(2,2*round(badge.height*scale/2)))
            frame=Image.new('RGBA',badge.size)
            frame.paste(badge.resize(size,Image.Resampling.LANCZOS),(0,0))
            frame.save(sequence/f'{index:04d}.png')
        output=folder/'subscribe-animation.mov'
        run_ffmpeg(['-framerate',str(FPS),'-i',str(sequence/'%04d.png'),
                    '-frames:v',str(frames),'-an','-c:v','qtrle','-threads','1',
                    '-pix_fmt','argb',output.name],folder,cancel,watch_output=output)
    return output,badge.height


def add_snow_filters(filters, source, folder, width, height):
    """Scroll two sparse, transparent snow layers continuously over the video."""
    from random import Random
    from PIL import Image, ImageDraw

    rng = Random(27)
    scale = min(width, height) / 720
    density = width * height / (1280 * 720 * scale ** 2)
    for layer, count, radius, opacity, dx, dy in (
        (0, 47, (.65, 1.55), (58, 136), 20, 30),
        (1, 24, (1.2, 2.7), (104, 190), 38, 57),
    ):
        filename = f'snow-{layer}.png'
        # Keep snow sparse and soften the edges of each dot before compositing.
        mask = Image.new('L', (width * 2, height * 2))
        draw = ImageDraw.Draw(mask)
        for _ in range(round(count * density)):
            x = rng.randrange(6, mask.width - 6)
            y = rng.randrange(6, mask.height - 6)
            r = rng.uniform(*radius) * scale * 2
            draw.ellipse((x-r, y-r, x+r, y+r), fill=rng.randint(*opacity))
        snow = Image.new('RGBA', (width, height), (247, 251, 255, 255))
        snow.putalpha(mask.resize(snow.size, Image.Resampling.LANCZOS))
        snow.save(folder/filename)
        filters.append(
            f'movie={filename}:dec_threads=1,loop=loop=-1:size=1:start=0,settb=1/{FPS},setpts=N,'
            f'format=yuva444p,scroll=h={-dx * scale / (FPS * width):.9f}:'
            f'v={-dy * scale / (FPS * height):.9f}[snow{layer}]'
        )
        filters.append(f'[{source}][snow{layer}]overlay=shortest=1[snowed{layer}]')
        source = f'snowed{layer}'
    return source


def render(project, assets_folder, output_folder, update):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Cần cài FFmpeg và ffprobe.')
    output_folder=Path(output_folder);output_folder.mkdir(parents=True,exist_ok=True)
    cancel=output_folder/'cancel'
    durations=plan(project,assets_folder); total=sum(durations); cfg=project['settings']
    story=project.get('story',{}).get('enabled',False)
    portrait_layout = story and project['story'].get('pixabay_aspect') == '9:16'
    voice_name=(project.get('voice_track') if story else None) or project.get('voice')
    if story:total=probe(asset(assets_folder,voice_name))['duration']
    if project.get('captions') or project.get('subtitle_text','').strip():
        capabilities=subprocess.run(['ffmpeg','-hide_banner','-filters'],capture_output=True,text=True,timeout=10,creationflags=NO_WINDOW).stdout
        if ' subtitles ' not in capabilities:
            raise ValueError('FFmpeg hiện tại chưa có bộ lọc phụ đề libass. Trên Mac: brew install ffmpeg-full, sau đó khởi động lại V3.')
    if project.get('captions'):
        validate_srt(asset(assets_folder,project['captions']).read_text(encoding='utf-8-sig'),total)
    short=cfg['resolution']
    width,height={'9:16':(short,round(short*16/9)), '16:9':(round(short*16/9),short),'1:1':(short,short)}[cfg['aspect']]
    width+=width%2;height+=height%2
    threads=max(2,min(8,(os.cpu_count() or 4)//2))
    video_encode=['-c:v','libx264','-preset','veryfast','-crf','20','-threads',str(threads),'-pix_fmt','yuv420p',
                  '-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv']
    audio_encode=['-c:a','aac','-ar','48000','-ac','2']
    encode=video_encode+audio_encode
    separate_audio = story and voice_name and cfg['original_volume'] == 0
    for i,(scene,seconds) in enumerate(zip(project['scenes'],durations)):
        update(5+65*i/len(durations),f'Đang dựng cảnh {i+1}/{len(durations)}')
        path=asset(assets_folder,scene['file']); media=probe(path)
        image=path.suffix.lower() in IMAGES
        args=(['-loop','1','-framerate',str(FPS)] if image else ['-stream_loop','-1'])+['-i',str(path)]
        if separate_audio:
            scene_audio = ['-an']
        else:
            audio = '0:a:0'
            if image or not media['audio']:
                args += ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
                audio = '1:a:0'
            scene_audio = ['-map',audio,'-af',
                           f'aresample=48000,apad,atrim=duration={seconds},asetpts=PTS-STARTPTS',*audio_encode]
        vf=f'fps={FPS},scale={width}:{height}:force_original_aspect_ratio='+('increase' if cfg['fit']=='cover' else 'decrease')
        vf+=f',crop={width}:{height}' if cfg['fit']=='cover' else f',pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black'
        # Stream-copy concatenation preserves each scene's H.264 color metadata.
        # Normalize both pixels and tags before concatenating, otherwise mixed
        # bt709/smpte170m sources can reinitialize the final effect graph.
        tail=(',scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,'
              'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,'
              'setsar=1,setpts=PTS-STARTPTS')
        if cfg['transition']=='fade':
            fade=min(.25,seconds/3);tail+=f',fade=t=in:st=0:d={fade},fade=t=out:st={seconds-fade}:d={fade}'
        if portrait_layout and 0 < media['width'] < media['height']:
            video_filters = ['-filter_complex', portrait_blur_filter(width, height, f',fps={FPS}'+tail),
                             '-map', '[framed]']
        else:
            video_filters = ['-map','0:v:0','-vf',vf+tail]
        reused=cached_ffmpeg(args+video_filters+scene_audio+['-t',str(seconds),*video_encode,f'scene-{i:04}.mp4'],
                            output_folder,cancel,inputs=[path])
        if reused:update(5+65*(i+1)/len(durations),f'Dùng lại cảnh đã dựng {i+1}/{len(durations)}')
    concat=''.join(f"file 'scene-{i:04}.mp4'\nduration {d:.9f}\n" for i,d in enumerate(durations))
    if story:
        # Repeat the normalized scene sequence without seeking an infinite concat input.
        cycle_frames = sum(round(seconds * FPS) for seconds in durations)
        concat *= (math.ceil(total * FPS) + cycle_frames - 1) // cycle_frames
    concat_path=output_folder/'scenes.txt'
    if not concat_path.exists() or concat_path.read_text()!=concat:
        concat_path.write_text(concat)
    # All scenes already have the same geometry/pixel format. Keep finite PNG
    # and movie sources alive even if an older cached stream changes color tags.
    args = ['-reinit_filter:v:0','0','-f','concat','-safe','1','-i','scenes.txt']
    if separate_audio:
        # Final filters read one regular video stream, without concat demuxing or unused scene audio.
        update(70, 'Đang nối các cảnh đã dựng')
        background = output_folder/'background.mp4'
        cached_ffmpeg(args+['-map','0:v:0','-c:v','copy',background.name],
                      output_folder,cancel,watch_output=background,
                      inputs=[concat_path,*[output_folder/f'scene-{i:04}.mp4' for i in range(len(durations))]])
        args = ['-reinit_filter:v:0','0','-i',background.name]
    audio_args = [] if separate_audio else args
    filters = []
    mix = []
    if not separate_audio:
        filters.append(f'[0:a]volume={cfg["original_volume"]}[base]')
        mix.append('[base]')
    index = 0 if separate_audio else 1
    if voice_name:
        audio_args+=['-i',str(asset(assets_folder,voice_name))]
        filters.append(f'[{index}:a]aresample=48000,apad,atrim=duration={total},asetpts=PTS-STARTPTS,volume={cfg["voice_volume"]}[voice]');index+=1
        if project.get('music') and cfg['duck']:
            filters.append('[voice]asplit=2[voiceout][side]');mix.append('[voiceout]')
        else: mix.append('[voice]')
    if project.get('music'):
        audio_args+=['-stream_loop','-1','-i',str(asset(assets_folder,project['music']))]
        filters.append(f'[{index}:a]aresample=48000,atrim=duration={total},asetpts=PTS-STARTPTS,volume={cfg["music_volume"]}[music]')
        if voice_name and cfg['duck']:
            filters.append('[music][side]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[duck]');mix.append('[duck]')
        else: mix.append('[music]')
        index += 1
    filters.append(''.join(mix)+f'amix=inputs={len(mix)}:duration=longest:normalize=0,alimiter=limit=0.95:latency=1[audio]')
    if separate_audio:
        update(71, 'Đang xử lý giọng đọc và âm thanh')
        soundtrack = output_folder/'soundtrack.m4a'
        cached_ffmpeg(audio_args+['-filter_complex',';'.join(filters),'-map','[audio]','-t',str(total),
                                  *audio_encode,soundtrack.name],output_folder,cancel,watch_output=soundtrack,
                      inputs=[asset(assets_folder,name) for name in (voice_name,project.get('music')) if name])
        filters = []
        index = 1
    source_video='0:v'
    if story and project.get('overlay_image'):
        overlay=project.get('story',{})
        size=float(overlay.get('width',75));x=float(overlay.get('x',50));y=float(overlay.get('y',100))
        if not 10<=size<=100 or not 0<=x<=100 or not 0<=y<=100:raise ValueError('Vị trí hoặc kích thước nhân vật không hợp lệ.')
        opacity=overlay.get('image_opacity',100)
        if type(opacity) is not int or not 0<=opacity<=100:raise ValueError('Độ hiển thị ảnh phải từ 0 đến 100%.')
        args+=['-i',str(asset(assets_folder,project['overlay_image']))]
        alpha=f',colorchannelmixer=aa={opacity/100:.4f}' if opacity!=100 else ''
        filters.append(f'[{index}:v]scale={round(width*size/100)}:{round(height*.95)}:force_original_aspect_ratio=decrease,format=rgba{alpha}[character]')
        filters.append(f'[0:v][character]overlay=x=(W-w)*{x/100}:y=(H-h)*{y/100}:eof_action=repeat[composite]')
        source_video='composite'
        index += 1
    if project.get('story', {}).get('snow_overlay', False):
        source_video = add_snow_filters(filters, source_video, output_folder, width, height)
    subtitles=''
    if project.get('captions'):
        subtitles=validate_srt(asset(assets_folder,project['captions']).read_text(encoding='utf-8-sig'),total)
    elif project.get('subtitle_text','').strip(): subtitles=estimated_srt(project['subtitle_text'],total)
    if subtitles:
        (output_folder/'captions.srt').write_text(subtitles,encoding='utf8')
        data = None
        if project.get('caption_words') and project.get('captions_origin')=='asr':
            data=json.loads(asset(assets_folder,project['caption_words']).read_text(encoding='utf8'))
            if data.get('source_voice')!=voice_name:
                raise ValueError('Phụ đề nhận diện thuộc file giọng đọc khác. Hãy nhận diện lại.')
        highlight_words = cfg.get('subtitle_mode', 'words') == 'words'
        if data is not None and not portrait_layout and (highlight_words or not story):
            from .speech import to_ass
            ass=to_ass(data,total,width,height,cfg['font_size'],highlight_words)
            (output_folder/'captions.ass').write_text(ass,encoding='utf8')
            filters.append(f'[{source_video}]subtitles=captions.ass[video]')
        else:
            style = f"PlayResX={width},PlayResY={height},FontName=Arial,FontSize={cfg['font_size']},Shadow=0,MarginL=32,MarginR=32"
            if story:
                style += ',PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,Bold=-1,Outline=3'
            else:
                style += ',Outline=2'
            style += f',MarginV={round(height*.12) if portrait_layout else 40}'
            filters.append(f"[{source_video}]subtitles=captions.srt:force_style='{style}'[video]")
        video='[video]'
    else: video=f'[{source_video}]' if source_video!='0:v' else '0:v:0'
    if project.get('story', {}).get('subscribe_corner', STORY_DEFAULTS['subscribe_corner']):
        sticker = output_folder/'subscribe.png'
        sticker_width = draw_subscribe_sticker(sticker, width, height)
        base_video = video if video.startswith('[') else f'[{video}]'
        margin = round(min(width, height) * .025)
        # Leave room for the move and the corner badge even on short videos.
        move_duration = min(.4, total / 4)
        intro_duration = min(5, total - 2 * move_duration)
        move = f'min(1,max(0,(t-{intro_duration:.6f})/{move_duration:.6f}))'
        corner_scale = min(width, height) * .21 / sticker_width
        scale = f'1-{1-corner_scale:.6f}*{move}'
        update(71,'Đang chuẩn bị hiệu ứng Subscribe')
        animation,sticker_height=prepare_subscribe_clip(
            output_folder,sticker,intro_duration,move_duration,corner_scale,cancel)
        filters.append(
            f'movie={animation.name}:dec_threads=1,settb=1/{FPS},setpts=N,format=rgba[subscribe]'
        )
        filters.append(
            f"{base_video}[subscribe]overlay="
            f"x='(W-{sticker_width}*({scale}))/2*(1-{move})+{margin}*{move}':"
            f"y='(H-{sticker_height}*({scale}))/2*(1-{move})+{margin}*{move}':"
            f'eof_action=repeat:repeatlast=1[with_subscribe]'
        )
        video = '[with_subscribe]'
    update(72, 'Đang xử lý phụ đề, hiệu ứng và xuất video')
    pending = output_folder/'output.pending.mp4'
    if separate_audio:
        picture = output_folder/'picture.mp4'
        if filters:
            run_ffmpeg(args+['-filter_complex',';'.join(filters),'-map',video,'-an','-t',str(total),
                             '-r',str(FPS),*video_encode,picture.name],
                       output_folder,cancel,lambda fraction:update(72+24*fraction,'Đang mã hóa hình ảnh'),
                       total,watch_output=picture)
        else:
            picture=background
        update(97, 'Đang ghép hình ảnh và âm thanh vào MP4')
        run_ffmpeg(['-i',picture.name,'-i',soundtrack.name,'-map','0:v:0','-map','1:a:0',
                    '-t',str(total),'-c','copy','-movflags','+faststart',pending.name],
                   output_folder,cancel,watch_output=pending)
    else:
        run_ffmpeg(args+['-filter_complex',';'.join(filters),'-map',video,'-map','[audio]',
                         '-t',str(total),'-r',str(FPS),*encode,'-movflags','+faststart',pending.name],
                   output_folder,cancel,lambda fraction:update(72+27*fraction,'Đang xuất MP4'),
                   total,watch_output=pending)
    result=probe(pending)
    if not result['video'] or not result['audio'] or abs(result['duration']-total)>.3:
        raise ValueError('Video xuất chưa đạt kiểm tra thời lượng/âm thanh.')
    pending.replace(output_folder/'output.mp4')
    if separate_audio:
        for temporary in {background,picture,soundtrack}:
            temporary.unlink(missing_ok=True)
    update(100,'Hoàn thành và đã lưu MP4')
    return dict(duration=total,width=width,height=height,scenes=len(durations))

