"""User-triggered Pixabay video search/download, cached and capped per project."""
from . import locking as fcntl
import random
import re
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from uuid import uuid4
from .projects import home, read, atomic, asset
from .render import probe, Cancelled

LIMIT=15
MAX_BYTES=500*1024*1024


def save_key(value):
    value=value.strip()
    if not value or len(value)>300:raise ValueError('Khóa Pixabay không hợp lệ.')
    path=home()/'pixabay-key.json'
    atomic(path,{'key':value});path.chmod(0o600)


def api_key():
    path=home()/'pixabay-key.json'
    return read(path).get('key','') if path.exists() else ''


def search(query, page=1):
    query=query.strip()
    if not 1<=len(query)<=100:raise ValueError('Từ khóa Pixabay cần từ 1 đến 100 ký tự.')
    key=api_key()
    if not key:raise ValueError('Chưa lưu khóa Pixabay. Nhập khóa trong mục Cấu hình Pixabay.')
    cache=home()/'pixabay-cache';cache.mkdir(exist_ok=True)
    filename=cache/(hashlib.sha256((query.casefold()+'|'+str(page)).encode()).hexdigest()+'.json')
    if filename.exists() and time.time()-filename.stat().st_mtime<86400:return read(filename)['hits']
    url='https://pixabay.com/api/videos/?'+urlencode(dict(key=key,q=query,page=page,per_page=50,safesearch='true'))
    try:
        with urlopen(Request(url,headers={'User-Agent':'LMTStudioPro/3'}),timeout=25) as response:
            body=response.read(4*1024*1024+1)
            if len(body)>4*1024*1024:raise ValueError('Phản hồi Pixabay quá lớn.')
            data=json.loads(body)
    except HTTPError as exc:
        raise ValueError('Pixabay trả lỗi HTTP '+str(exc.code)+'. Kiểm tra khóa hoặc thử lại sau.') from None
    except (URLError,TimeoutError):raise ValueError('Chưa kết nối được Pixabay. Kiểm tra Internet và thử lại.') from None
    hits=[]
    for item in data.get('hits',[]):
        choices=[v for v in item.get('videos',{}).values() if v.get('width',0)>=640 and v.get('size',MAX_BYTES+1)<=MAX_BYTES]
        if not choices:continue
        hd=[v for v in choices if v['width']>=1280]
        video=min(hd or choices,key=lambda v:v.get('size',MAX_BYTES))
        hits.append(dict(id=int(item['id']),url=video['url'],width=video['width'],height=video['height'],
                         duration=item.get('duration',0),pageURL=item['pageURL'],user=item.get('user',''),tags=item.get('tags','')))
    atomic(filename,{'hits':hits})
    return hits


def related_queries(query):
    """Conservative synonyms, never an unrelated generic fallback."""
    query = query.strip()
    groups = [
        (('forest','woodland','woods','rừng'), ('forest','woodland','woods','forest trees')),
        (('ocean','sea','beach','biển'), ('ocean','sea','coast','beach')),
        (('river','stream','sông','suối'), ('river','stream','flowing river','river water')),
        (('mountain','mountains','núi'), ('mountains','mountain landscape','mountain peaks')),
        (('waterfall','thác'), ('waterfall','waterfalls','cascading water')),
        (('city','urban','thành phố'), ('city','urban','cityscape')),
        (('rain','rainfall','mưa'), ('rain','rainfall','rain drops')),
        (('flower','flowers','hoa'), ('flowers','flower garden','blooming flowers')),
        (('cloud','clouds','mây'), ('clouds','cloudy sky','moving clouds')),
    ]
    results = [query]
    for words, synonyms in groups:
        for word in words:
            pattern = r'(?<!\w)' + re.escape(word) + r'(?!\w)'
            if re.search(pattern, query, re.IGNORECASE):
                results.extend(re.sub(pattern, term, query, flags=re.IGNORECASE) for term in synonyms)
                break
    return list(dict.fromkeys(q for q in results if 1 <= len(q) <= 100))[:5]


def select_for_project(folder, query, preferred=None, cancel=None):
    """Reserve 15 distinct IDs atomically across projects; retain on retries."""
    folder = Path(folder)
    reservation = folder/'pixabay-selection.json'
    with (home()/'pixabay-history.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if reservation.exists():
            return read(reservation)['hits']
        history_file = home()/'pixabay-history.json'
        history = read(history_file) if history_file.exists() else {}
        # Include downloads from projects created before the shared history.
        for manifest in home().glob('*/pixabay-downloads.json'):
            for key in read(manifest):
                history.setdefault(key, manifest.parent.name)
        used = set(history)
        candidates = {}
        def add(hits):
            for hit in hits:
                key = str(int(hit['id']))
                if key not in used:
                    candidates.setdefault(key, hit)
        add(preferred or [])
        queries = related_queries(query)
        requests = 0
        for term in queries:
            if len(candidates) >= LIMIT or requests >= 10: break
            for page in range(1, (10 if len(queries) == 1 else 2) + 1):
                if len(candidates) >= LIMIT or requests >= 10: break
                if cancel is not None and cancel.exists(): raise Cancelled()
                hits = search(term, page=page)
                requests += 1
                add(hits)
                if not hits: break
        if len(candidates) < LIMIT:
            raise ValueError(f'Chỉ còn {len(candidates)} video Pixabay mới theo từ khóa này; cần 15 video không trùng phiên trước. Đã thử các từ khóa gần nghĩa phù hợp; hãy nhập chủ đề rộng hơn rồi dựng lại.')
        hits = list(candidates.values())
        random.SystemRandom().shuffle(hits)
        chosen = hits[:LIMIT]
        for hit in chosen: history[str(hit['id'])] = folder.name
        # History first: a crash can reserve unused IDs but never duplicate them.
        atomic(history_file, history)
        atomic(reservation, dict(query=query, searched_queries=queries, hits=chosen))
        return chosen


def safe_url(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='cdn.pixabay.com' or parsed.port not in (None,443):
        raise ValueError('Chỉ tải video từ CDN chính thức của Pixabay.')
    return url


class CDNRedirect(__import__('urllib.request',fromlist=['HTTPRedirectHandler']).HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download(folder, selected, cancel, update):
    """Manifest counts successful distinct clips across every retry of this project."""
    if len(selected)>LIMIT:raise ValueError('Mỗi dự án tối đa 15 video Pixabay.')
    folder=Path(folder);manifest=folder/'pixabay-downloads.json'
    records=read(manifest) if manifest.exists() else {}
    if len(set(records)|{str(int(hit['id'])) for hit in selected})>LIMIT:
        raise ValueError('Dự án đã đạt giới hạn 15 video Pixabay khác nhau. Hãy dùng lại video đã tải.')
    from urllib.request import build_opener
    opener=build_opener(CDNRedirect())
    result=[]
    for i,hit in enumerate(selected):
        if cancel.exists():raise Cancelled()
        key=str(int(hit['id']));existing=records.get(key)
        if existing:
            try:asset(folder,existing['file']);result.append(existing['file']);continue
            except ValueError:pass
        update(i/max(1,len(selected)),f'Đang tải video Pixabay {i+1}/{len(selected)}')
        url=safe_url(hit['url']);name=uuid4().hex+'.mp4';target=folder/'assets'/name;partial=target.with_suffix('.part')
        try:
            with opener.open(Request(url,headers={'User-Agent':'LMTStudioPro/3'}),timeout=25) as response,partial.open('wb') as dest:
                safe_url(response.geturl());size=0
                while True:
                    if cancel.exists():raise Cancelled()
                    chunk=response.read(256*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>MAX_BYTES:raise ValueError('Video Pixabay vượt 500 MB.')
                    dest.write(chunk)
            if not probe(partial)['video']:raise ValueError('Tệp Pixabay không phải video hợp lệ.')
            partial.replace(target)
            records[key]=dict(file=name,pageURL=hit.get('pageURL',''),user=hit.get('user',''))
            atomic(manifest,records);result.append(name)
        except (HTTPError,URLError,TimeoutError):raise ValueError('Chưa tải xong video Pixabay. Các video đã tải vẫn được giữ; có thể thử lại.') from None
        finally:
            if partial.exists():partial.unlink()
    return list(dict.fromkeys(result))
