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
        (('snow','snowy','tuyết'), ('snow','snowy landscape','snowfall')),
        (('winter','mùa đông'), ('winter','winter scenery','winter landscape')),
        (('lake','hồ nước'), ('lake','lakeside','lake scenery')),
        (('garden','vườn'), ('garden','garden scenery','garden plants')),
        (('countryside','đồng quê'), ('countryside','rural landscape','farmland')),
        (('desert','sa mạc'), ('desert','sand dunes','desert landscape')),
        (('sunset','hoàng hôn'), ('sunset','evening sky','sunset scenery')),
        (('mansion','villa','biệt thự'), ('mansion','villa','luxury house')),
        (('living room','phòng khách'), ('living room','home interior','lounge interior')),
        (('office','văn phòng'), ('office','workplace','office workspace')),
        (('kitchen','nhà bếp'), ('kitchen','home kitchen','kitchen room')),
        (('restaurant','nhà hàng'), ('restaurant','dining room','restaurant dining')),
        (('hospital','bệnh viện'), ('hospital','hospital corridor','hospital room')),
        (('school','trường học'), ('school','school building','school campus')),
        (('castle','lâu đài'), ('castle','stone castle','historic castle')),
        (('church','nhà thờ'), ('church','church building','church architecture')),
        (('celebration','bữa tiệc'), ('celebration','festivity','party decorations')),
    ]
    results = [query]
    for words, synonyms in groups:
        for word in words:
            pattern = r'(?<!\w)' + re.escape(word) + r'(?!\w)'
            if re.search(pattern, query, re.IGNORECASE):
                results.extend(re.sub(pattern, term, query, flags=re.IGNORECASE) for term in synonyms)
                break
    return list(dict.fromkeys(q for q in results if 1 <= len(q) <= 100))[:5]


def select_for_project(folder, query, preferred=None, cancel=None, update=lambda _:None):
    """Mix related queries within ten requests; reserve fresh IDs atomically."""
    folder = Path(folder)
    reservation = folder/'pixabay-selection.json'
    with (home()/'pixabay-history.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if reservation.exists():
            update('Dùng lại 15 video Pixabay đã chọn cho dự án này')
            return read(reservation)['hits']
        history_file = home()/'pixabay-history.json'
        history = read(history_file) if history_file.exists() else {}
        for manifest in home().glob('*/pixabay-downloads.json'):
            for key in read(manifest):
                history.setdefault(key, manifest.parent.name)
        used = set(history)
        chosen = []
        chosen_ids = set()
        def take(hit):
            key = str(int(hit['id']))
            if key in used or key in chosen_ids: return False
            chosen.append(hit); chosen_ids.add(key)
            return True
        for hit in preferred or []:
            if len(chosen) >= LIMIT: break
            take(hit)
        queries = related_queries(query)
        pools = [[] for _ in queries]
        pages = [1 for _ in queries]
        exhausted = set()
        searched = []
        requests = 0
        rng = random.SystemRandom()
        def fill():
            # Round-robin selection avoids letting the first query take all slots.
            while len(chosen) < LIMIT:
                added = False
                for pool in pools:
                    while pool:
                        if take(pool.pop()):
                            added = True
                            break
                    if len(chosen) >= LIMIT: break
                if not added: break
        # Initially sample up to three closely related queries even if one is plentiful.
        # Extra pages/terms are fetched only when those cannot supply fifteen fresh IDs.
        initial = min(3, len(queries))
        pending = list(range(initial))
        while len(chosen) < LIMIT and requests < 10:
            if cancel is not None and Path(cancel).exists(): raise Cancelled()
            if not pending:
                pending = [i for i in range(len(queries)) if i not in exhausted]
                if not pending: break
            i = pending.pop(0)
            term = queries[i]
            update(f'Tìm Pixabay {requests+1}/10 · {term} · đã chọn {len(chosen)}/15 video mới')
            hits = search(term, page=pages[i])
            pages[i] += 1; requests += 1
            if term not in searched: searched.append(term)
            if not hits: exhausted.add(i)
            fresh = [h for h in hits if str(int(h['id'])) not in used]
            rng.shuffle(fresh); pools[i].extend(fresh)
            if requests >= initial: fill()
        if len(chosen) < LIMIT:
            raise ValueError(f'Chỉ còn {len(chosen)} video Pixabay mới theo từ khóa này; cần 15 video không trùng phiên trước. Đã thử các từ khóa gần nghĩa phù hợp; hãy nhập chủ đề rộng hơn rồi dựng lại.')
        if cancel is not None and Path(cancel).exists(): raise Cancelled()
        rng.shuffle(chosen)
        for hit in chosen: history[str(hit['id'])] = folder.name
        # History first: a crash can reserve unused IDs but never duplicate them.
        atomic(history_file, history)
        atomic(reservation, dict(query=query, searched_queries=searched, search_requests=requests, hits=chosen))
        update(f'Đã chọn 15 video Pixabay mới từ {len(searched)} từ khóa liên quan')
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

