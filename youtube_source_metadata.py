"""Best-effort public YouTube metadata. No cookies, API keys or video download."""
import json
import re
import time
import requests

MAX_PAGE_BYTES=8*1024*1024

def parse_player_metadata(page, video_id):
    decoder=json.JSONDecoder()
    for marker in re.finditer(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*',page):
        try:data,_=decoder.raw_decode(page,marker.end())
        except ValueError:continue
        details=data.get('videoDetails',{}) if isinstance(data,dict) else {}
        if not isinstance(details,dict) or details.get('videoId')!=video_id:continue
        title=details.get('title');description=details.get('shortDescription')
        tags=details.get('keywords')
        result={'video_id':video_id,'status':{}}
        for field,value,limit in [('title',title,2000),('description',description,20000)]:
            if isinstance(value,str) and len(value)<=limit:
                result[field]=value;result['status'][field]='fetched' if value else 'empty'
            else:result['status'][field]='unavailable'
        if tags is None:
            # Missing keywords is not evidence that the creator supplied no tags.
            result['status']['tags']='unavailable'
        elif isinstance(tags,list) and all(isinstance(t,str) for t in tags) and sum(map(len,tags))<=10000:
            result['tags']=tags;result['status']['tags']='fetched' if tags else 'empty'
        else:result['status']['tags']='unavailable'
        return result
    return {'video_id':video_id,'status':dict.fromkeys(('title','description','tags'),'unavailable')}

def fetch_source_metadata(video_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):raise ValueError('Mã video YouTube không hợp lệ.')
    result={'video_id':video_id,'status':dict.fromkeys(('title','description','tags'),'unavailable')}
    try:
        with requests.get('https://www.youtube.com/watch',params={'v':video_id,'hl':'en'},
                          headers={'User-Agent':'Mozilla/5.0'},timeout=(5,12),stream=True,allow_redirects=False) as response:
            if response.ok and response.status_code==200:
                chunks=[];size=0;deadline=time.monotonic()+15
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>MAX_PAGE_BYTES or time.monotonic()>deadline:break
                    chunks.append(chunk)
                else:
                    result=parse_player_metadata(b''.join(chunks).decode('utf-8',errors='replace'),video_id)
    except (requests.RequestException,ValueError):pass
    if result['status']['title']=='unavailable':
        try:
            response=requests.get('https://www.youtube.com/oembed',params={'url':'https://www.youtube.com/watch?v='+video_id,'format':'json'},timeout=(5,8),allow_redirects=False)
            if response.status_code==200:
                title=response.json().get('title')
                if isinstance(title,str) and title.strip() and len(title)<=2000:
                    result['title']=title;result['status']['title']='fetched'
        except (requests.RequestException,ValueError,AttributeError):pass
    return result
