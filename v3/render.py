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
from .projects import asset, IMAGES, STORY_DEFAULTS

FPS = 30
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


def run_ffmpeg(args, folder, cancel, progress=None, duration=1):
    if cancel.exists(): raise Cancelled()
    base=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-filter_threads','1','-filter_complex_threads','1']
    with (folder/'ffmpeg.log').open('a') as log:
        process=subprocess.Popen(base+args+['-progress','pipe:1','-nostats'],stdout=subprocess.PIPE,stderr=log,text=True,cwd=folder,creationflags=NO_WINDOW)
        messages=queue.Queue()
        def read_progress():
            for line in process.stdout: messages.put(line.strip())
        reader=threading.Thread(target=read_progress,daemon=True);reader.start()
        try:
            while process.poll() is None:
                if cancel.exists(): raise Cancelled()
                try: line=messages.get(timeout=.2)
                except queue.Empty: continue
                if line:
                    if progress and line.startswith('out_time_us='):
                        try: progress(min(1,float(line.split('=')[1])/1e6/duration))
                        except ValueError: pass
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

    unit = min(width, height) / 720 * 1.12
    badge = Image.new('RGBA', (round(220 * unit), round(56 * unit)))
    draw = ImageDraw.Draw(badge)
    draw.rounded_rectangle((0, 0, badge.width - 1, badge.height - 1),
                           radius=round(12 * unit), fill='#cc1528')
    draw.polygon([(round(x * unit), round(y * unit)) for x, y in
                  ((20, 16), (20, 40), (41, 28))], fill='white')
    try:
        font = ImageFont.load_default(size=round(28 * unit))
    except TypeError:  # Pillow versions before scalable default fonts.
        font = ImageFont.load_default()
    draw.text((round(130 * unit), badge.height // 2), 'Subscribe',
              fill='white', font=font, anchor='mm')
    badge.save(path)


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
    encode=['-c:v','libx264','-preset','veryfast','-crf','20','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2']
    for i,(scene,seconds) in enumerate(zip(project['scenes'],durations)):
        update(5+65*i/len(durations),f'Đang dựng cảnh {i+1}/{len(durations)}')
        path=asset(assets_folder,scene['file']); media=probe(path)
        image=path.suffix.lower() in IMAGES
        args=(['-loop','1','-framerate',str(FPS)] if image else ['-stream_loop','-1'])+['-i',str(path)]
        if image or not media['audio']:
            args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo'];audio='1:a:0'
        else: audio='0:a:0'
        vf=f'fps={FPS},scale={width}:{height}:force_original_aspect_ratio='+('increase' if cfg['fit']=='cover' else 'decrease')
        vf+=f',crop={width}:{height}' if cfg['fit']=='cover' else f',pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black'
        tail=',setsar=1,setpts=PTS-STARTPTS'
        if cfg['transition']=='fade':
            fade=min(.25,seconds/3);tail+=f',fade=t=in:st=0:d={fade},fade=t=out:st={seconds-fade}:d={fade}'
        if portrait_layout and 0 < media['width'] < media['height']:
            video_filters = ['-filter_complex', portrait_blur_filter(width, height, f',fps={FPS}'+tail),
                             '-map', '[framed]']
        else:
            video_filters = ['-map','0:v:0','-vf',vf+tail]
        run_ffmpeg(args+video_filters+['-map',audio,'-af',f'aresample=48000,apad,atrim=duration={seconds},asetpts=PTS-STARTPTS','-t',str(seconds),*encode,f'scene-{i:04}.mp4'],output_folder,cancel)
    concat=''.join(f"file 'scene-{i:04}.mp4'\nduration {d:.9f}\n" for i,d in enumerate(durations))
    (output_folder/'scenes.txt').write_text(concat)
    args=(['-stream_loop','-1'] if story else [])+['-f','concat','-safe','1','-i','scenes.txt']; filters=[f'[0:a]volume={cfg["original_volume"]}[base]'];mix=['[base]'];index=1
    if voice_name:
        args+=['-i',str(asset(assets_folder,voice_name))]
        filters.append(f'[{index}:a]aresample=48000,apad,atrim=duration={total},asetpts=PTS-STARTPTS,volume={cfg["voice_volume"]}[voice]');index+=1
        if project.get('music') and cfg['duck']:
            filters.append('[voice]asplit=2[voiceout][side]');mix.append('[voiceout]')
        else: mix.append('[voice]')
    if project.get('music'):
        args+=['-stream_loop','-1','-i',str(asset(assets_folder,project['music']))]
        filters.append(f'[{index}:a]aresample=48000,atrim=duration={total},asetpts=PTS-STARTPTS,volume={cfg["music_volume"]}[music]')
        if voice_name and cfg['duck']:
            filters.append('[music][side]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[duck]');mix.append('[duck]')
        else: mix.append('[music]')
        index += 1
    filters.append(''.join(mix)+f'amix=inputs={len(mix)}:duration=longest:normalize=0,alimiter=limit=0.95:latency=1[audio]')
    source_video='0:v'
    if story and project.get('overlay_image'):
        overlay=project.get('story',{})
        size=float(overlay.get('width',75));x=float(overlay.get('x',50));y=float(overlay.get('y',100))
        if not 10<=size<=100 or not 0<=x<=100 or not 0<=y<=100:raise ValueError('Vị trí hoặc kích thước nhân vật không hợp lệ.')
        args+=['-loop','1','-framerate',str(FPS),'-i',str(asset(assets_folder,project['overlay_image']))]
        filters.append(f'[{index}:v]scale={round(width*size/100)}:{round(height*.95)}:force_original_aspect_ratio=decrease,format=rgba[character]')
        filters.append(f'[0:v][character]overlay=x=(W-w)*{x/100}:y=(H-h)*{y/100}:shortest=1[composite]')
        source_video='composite'
        index += 1
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
        if data is not None and not portrait_layout:
            from .speech import to_ass
            ass=to_ass(data,total,width,height,cfg['font_size'],cfg.get('subtitle_mode','words')=='words')
            (output_folder/'captions.ass').write_text(ass,encoding='utf8')
            filters.append(f'[{source_video}]subtitles=captions.ass[video]')
        else:
            style = f"PlayResX={width},PlayResY={height},FontName=Arial,FontSize={cfg['font_size']},Shadow=0,MarginL=32,MarginR=32"
            style += (f',PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,Bold=-1,Outline=3,MarginV={round(height*.12)}'
                      if portrait_layout else ',Outline=2,MarginV=40')
            filters.append(f"[{source_video}]subtitles=captions.srt:force_style='{style}'[video]")
        video='[video]'
    else: video='[composite]' if source_video=='composite' else '0:v:0'
    if project.get('story', {}).get('subscribe_corner', STORY_DEFAULTS['subscribe_corner']):
        sticker = output_folder/'subscribe.png'
        draw_subscribe_sticker(sticker, width, height)
        base_video = video if video.startswith('[') else f'[{video}]'
        margin = round(min(width, height) * .025)
        # Leave room for the move and the corner badge even on short videos.
        move_duration = min(.4, total / 4)
        intro_duration = min(5, total - 2 * move_duration)
        # After the move, overlay repeats the last frame of the small badge.
        sticker_duration = intro_duration + move_duration + 2 / FPS
        args += ['-loop', '1', '-framerate', str(FPS), '-t', f'{sticker_duration:.6f}', '-i', sticker.name]
        growth = f'min(1,max(0,t/{intro_duration:.6f}))'
        move = f'min(1,max(0,(t-{intro_duration:.6f})/{move_duration:.6f}))'
        corner_scale = .68 / 1.12
        scale = f'(.55+.45*{growth})*(1-{move})+{corner_scale:.6f}*{move}'
        filters.append(
            f"[{index}:v]scale=w='2*round(iw*({scale})/2)':h=-2:eval=frame[subscribe]"
        )
        filters.append(
            f"{base_video}[subscribe]overlay="
            f"x='(W-w)/2*(1-{move})+{margin}*{move}':"
            f"y='(H-h)/2*(1-{move})+{margin}*{move}'[with_subscribe]"
        )
        video = '[with_subscribe]'
    update(72,'Đang ghép âm thanh, phụ đề và xuất MP4')
    run_ffmpeg(args+['-filter_complex',';'.join(filters),'-map',video,'-map','[audio]','-t',str(total),'-r',str(FPS),*encode,'-movflags','+faststart','output.pending.mp4'],output_folder,cancel,
               lambda fraction:update(72+27*fraction,'Đang xuất MP4'),total)
    result=probe(output_folder/'output.pending.mp4')
    if not result['video'] or not result['audio'] or abs(result['duration']-total)>.3:
        raise ValueError('Video xuất chưa đạt kiểm tra thời lượng/âm thanh.')
    (output_folder/'output.pending.mp4').replace(output_folder/'output.mp4')
    update(100,'Hoàn thành và đã lưu MP4')
    return dict(duration=total,width=width,height=height,scenes=len(durations))

