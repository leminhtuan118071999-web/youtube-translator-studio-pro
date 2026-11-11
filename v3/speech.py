"""Local multilingual speech recognition and word-timed subtitle formatting."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import sys
from .projects import asset, atomic, home, read
from .render import probe, timestamp


def normalize_words(segments, duration, allow_empty=False):
    words=[];previous=0.0
    for segment in segments:
        for word in segment.words or []:
            text=str(word.word)
            if not text.strip():continue
            start=float(word.start);end=float(word.end)
            if not math.isfinite(start) or not math.isfinite(end):raise ValueError('Mốc nhận diện không hợp lệ.')
            start=max(previous,0,start);end=min(duration,max(start+.01,end))
            if end<=start:continue
            words.append(dict(start=round(start,3),end=round(end,3),text=text))
            previous=end
    if not words and not allow_empty:raise ValueError('Không phát hiện được lời nói rõ ràng trong file giọng đọc.')
    return words


def check_words(data, duration):
    if not isinstance(data,dict) or not isinstance(data.get('words'),list) or not data['words']:
        raise ValueError('Chưa có mốc phụ đề theo từng từ.')
    if len(data['words'])>200000:raise ValueError('Dữ liệu phụ đề quá lớn.')
    previous=0
    for word in data['words']:
        a,b=word.get('start'),word.get('end');text=word.get('text')
        if not isinstance(a,(float,int)) or not isinstance(b,(float,int)) or not math.isfinite(a+b) or not 0<=a<b<=duration+.15 or a<previous-.002:
            raise ValueError('Mốc thời gian từng từ không hợp lệ.')
        if not isinstance(text,str) or not text.strip() or len(text)>1000:
            raise ValueError('Văn bản từng từ không hợp lệ.')
        previous=b
    return data['words']


def groups(words):
    result=[];group=[]
    for word in words:
        if group and (len(group)>=6 or sum(len(w['text']) for w in group)+len(word['text'])>62 or word['end']-group[0]['start']>4 or word['start']-group[-1]['end']>.7):
            result.append(group);group=[]
        group.append(word)
        if word['text'].rstrip().endswith(('.', '!', '?', '。', '！', '？')):
            result.append(group);group=[]
    if group:result.append(group)
    return result


def to_srt(words):
    return '\n'.join(f'{i+1}\n{timestamp(group[0]["start"])} --> {timestamp(group[-1]["end"])}\n'+''.join(w['text'] for w in group).strip()+'\n' for i,group in enumerate(groups(words)))


def ass_time(value):
    centiseconds=round(value*100);seconds,cs=divmod(centiseconds,100);minutes,seconds=divmod(seconds,60);hours,minutes=divmod(minutes,60)
    return f'{hours}:{minutes:02}:{seconds:02}.{cs:02}'


def escaped(text):
    return text.replace('\\','＼').replace('{','（').replace('}','）').replace('\n',' ').replace('\r',' ')


def to_ass(data,duration,width,height,font_size,highlight=True):
    words=check_words(data,duration)
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,32,32,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    for group in groups(words):
        boundaries=sorted({w['start'] for w in group}|{w['end'] for w in group}) if highlight else [group[0]['start'],group[-1]['end']]
        for start,end in zip(boundaries,boundaries[1:]):
            if ass_time(end)==ass_time(start):continue
            text=''
            for word in group:
                active=highlight and word['start']<=start<word['end']
                text+=('{\\c&H00FFFF&}' if active else '{\\c&HFFFFFF&}')+escaped(word['text'])
            events.append(f'Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}')
    return header+'\n'.join(events)+'\n'


def transcribe(run,report=None):
    from faster_whisper import WhisperModel
    run=Path(run);project=read(run/'snapshot.json');folder=home()/project['id']
    if not project.get('voice'):raise ValueError('Hãy tải và lưu file giọng đọc trước.')
    audio=asset(folder,project['voice']);duration=probe(audio)['duration']
    if duration<=0:raise ValueError('File giọng đọc không có thời lượng hợp lệ.')
    model_name=project.get('asr_model','small')
    if model_name not in ('tiny','base','small'):raise ValueError('Model phụ đề không hợp lệ.')
    def update(progress,stage):
        if report:report(progress,stage)
        atomic(run/'status.json',dict(state='running',task='transcribe',progress=progress,stage=stage,updated=__import__('time').time()))
    update(2,'Đang nạp model nhận diện; lần đầu cần tải model qua Internet')
    model=WhisperModel(model_name,device='cpu',compute_type='int8',cpu_threads=min(4,os.cpu_count() or 2),
                       download_root=str(home()/'models'))
    update(5,'Đang nhận diện ngôn ngữ và thời điểm từng từ')
    segments,info=model.transcribe(str(audio),task='transcribe',language=None,word_timestamps=True,
                                    beam_size=5,vad_filter=True,condition_on_previous_text=False)
    words=[]
    for segment in segments:
        new=normalize_words([segment],duration,allow_empty=True)
        words.extend(new)
        update(min(97,5+round(92*segment.end/duration)),f'Đang nghe giọng đọc · ngôn ngữ {info.language}')
    # Validate globally, including segment boundaries; clamp tiny model overlaps.
    previous=0
    for word in words:
        word['start']=max(previous,word['start']);word['end']=max(word['start']+.001,word['end']);previous=word['end']
    data=dict(version=1,language=info.language,language_probability=info.language_probability,
              duration=duration,source_voice=project['voice'],model=model_name,words=words)
    check_words(data,duration)
    atomic(run/'words.json',data)
    (run/'captions.srt').write_text(to_srt(words),encoding='utf8')


if __name__=='__main__':
    try:transcribe(sys.argv[1])
    except Exception as exc:
        atomic(Path(sys.argv[1])/'speech-error.json',dict(error=str(exc)[-2000:]))
        raise
