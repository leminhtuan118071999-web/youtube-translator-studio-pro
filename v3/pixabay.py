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

LIMIT=20
MAX_BYTES=500*1024*1024


RATIOS = ('16:9', '9:16')


def matches_ratio(video, ratio='16:9'):
    width, height = video.get('width'), video.get('height')
    if ratio not in RATIOS or type(width) is not int or type(height) is not int:
        return False
    long_side, short_side = (width, height) if ratio == '16:9' else (height, width)
    return long_side > short_side > 0 and abs(long_side * 9 - short_side * 16) <= 16


def is_widescreen(video):
    return matches_ratio(video)


def selection_path(folder, ratio):
    if ratio not in RATIOS:
        raise ValueError('Tỷ lệ video Pixabay không hợp lệ.')
    filename = 'pixabay-selection.json' if ratio == '16:9' else 'pixabay-selection-9x16.json'
    return Path(folder)/filename


class WrongRatio(ValueError):
    def __init__(self, video_id, ratio, media):
        self.video_id = int(video_id)
        super().__init__(f'Video Pixabay {video_id} có kích thước {media["width"]}×{media["height"]}, '
                         f'không đúng tỷ lệ {ratio}. Hãy chọn video khác.')


def drop_reserved_video(folder, ratio, video_id):
    reservation = selection_path(folder, ratio)
    saved = read(reservation)
    saved['hits'] = [hit for hit in saved['hits'] if int(hit['id']) != video_id]
    atomic(reservation, saved)
    manifest = Path(folder)/'pixabay-downloads.json'
    if manifest.exists():
        records = read(manifest)
        if records.pop(str(video_id), None) is not None:
            atomic(manifest, records)


def ratio_records(records, ratio):
    # Downloads from older V3 versions used landscape exclusively.
    return {key: item for key, item in records.items() if item.get('aspect', '16:9') == ratio}


def save_key(value):
    value=value.strip()
    if not value or len(value)>300:raise ValueError('Khóa Pixabay không hợp lệ.')
    path=home()/'pixabay-key.json'
    atomic(path,{'key':value});path.chmod(0o600)


def api_key():
    path=home()/'pixabay-key.json'
    return read(path).get('key','') if path.exists() else ''


def search(query, page=1, *, ratio='16:9'):
    if ratio not in RATIOS:raise ValueError('Tỷ lệ video Pixabay không hợp lệ.')
    query=query.strip()
    if not 1<=len(query)<=100:raise ValueError('Từ khóa Pixabay cần từ 1 đến 100 ký tự.')
    key=api_key()
    if not key:raise ValueError('Chưa lưu khóa Pixabay. Nhập khóa trong mục Cấu hình Pixabay.')
    cache=home()/'pixabay-cache';cache.mkdir(exist_ok=True)
    filename=cache/(hashlib.sha256((ratio.replace(':','x')+'-v1|'+query.casefold()+'|'+str(page)).encode()).hexdigest()+'.json')
    if filename.exists() and time.time()-filename.stat().st_mtime<86400:return [h for h in read(filename)['hits'] if matches_ratio(h, ratio)]
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
        choices=[v for v in item.get('videos',{}).values() if matches_ratio(v, ratio) and max(v['width'], v['height'])>=640 and v.get('size',MAX_BYTES+1)<=MAX_BYTES]
        if not choices:continue
        hd=[v for v in choices if max(v['width'], v['height'])>=1280]
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


def diversity_queries(query):
    """Broaden familiar settings into related scenery, preserving explicit modifiers."""
    query=query.strip()
    groups=[
        (('forest','woodland','woods','rừng'), ('river','mountain landscape')),
        (('river nature','river','stream','sông','suối'), ('lake landscape','forest')),
        (('mountain landscape','mountains','mountain','núi'), ('lake landscape','forest')),
        (('lake landscape','lake','hồ nước'), ('river','mountain landscape')),
        (('waterfall nature','waterfall','thác'), ('river','forest')),
        (('ocean beach','ocean','beach','sea','biển'), ('rocky coast','seaside cliffs')),
        (('countryside','đồng quê'), ('farm fields','rural village')),
        (('flower garden','garden','vườn hoa'), ('blooming flowers','garden pathway')),
        (('desert landscape','desert','sa mạc'), ('sand dunes','desert rocks')),
        (('snow winter','snow','winter','tuyết'), ('snowy forest winter','snowy mountain winter')),
        (('city street','city','urban','thành phố'), ('city skyline','city park')),
        (('luxury interior','living room','phòng khách'), ('elegant home interior','home decor')),
        (('luxury mansion','mansion','villa','biệt thự'), ('villa garden','luxury house exterior')),
        (('office interior','office','văn phòng'), ('meeting room','office workspace')),
        (('restaurant interior','restaurant','nhà hàng'), ('dining table','restaurant kitchen')),
        (('school classroom','school','trường học'), ('school corridor','school campus')),
        (('hospital','bệnh viện'), ('hospital corridor','hospital exterior')),
        (('castle','lâu đài'), ('castle courtyard','castle exterior')),
        (('church','nhà thờ'), ('church exterior','church interior')),
    ]
    modifiers={'sunlight','sunrise','sunset','night','day','daytime','evening','morning',
               'winter','summer','autumn','spring','snow','snowy','rain','rainy',
               'fog','foggy','mist','misty','nature','landscape','scenery','peaceful',
               'quiet','green','golden','aerial','drone','4k','hd','luxury'}
    result=[query]; protected=set()
    for anchors,companions in groups:
        matched=False
        for anchor in anchors:
            pattern=r'(?<!\w)'+re.escape(anchor)+r'(?!\w)'
            match=re.search(pattern,query,re.IGNORECASE)
            if not match:continue
            # Unknown qualifiers (e.g. forest fire) must not create unrelated scenery.
            remaining=(query[:match.start()]+' '+query[match.end():]).casefold().split()
            if not set(remaining)<=modifiers:continue
            protected=set(remaining)
            result.extend(re.sub(pattern,term,query,flags=re.IGNORECASE) for term in companions)
            matched=True;break
        if matched:break
    result.extend(related_queries(query))
    return list(dict.fromkeys(q for q in result if 1<=len(q)<=100
                              and protected<=set(q.casefold().split())))[:7]


def select_for_project(folder, query, preferred=None, cancel=None, update=lambda _:None, *, ratio='16:9', allow_partial=False, excluded=()):
    """Mix related queries and top up automatic batches from other background themes."""
    folder = Path(folder)
    reservation = selection_path(folder, ratio)
    with (home()/'pixabay-history.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = read(reservation)['hits'] if reservation.exists() else []
        previous = [h for h in previous if matches_ratio(h, ratio) and str(h['id']) not in excluded]
        if len(previous) == LIMIT:
            update(f'Dùng lại {LIMIT} video Pixabay đã chọn cho dự án này')
            return previous
        history_file = home()/'pixabay-history.json'
        history = read(history_file) if history_file.exists() else {}
        for manifest in home().glob('*/pixabay-downloads.json'):
            for key in read(manifest):
                history.setdefault(key, manifest.parent.name)
        used = set(history).union(excluded)
        chosen = list(previous)
        chosen_ids = {str(int(hit['id'])) for hit in previous}
        def take(hit):
            if not matches_ratio(hit, ratio): return False
            key = str(int(hit['id']))
            if key in used or key in chosen_ids: return False
            chosen.append(hit); chosen_ids.add(key)
            return True
        for hit in preferred or []:
            if len(chosen) >= LIMIT: break
            take(hit)
        queries = diversity_queries(query)
        pools = [[] for _ in queries]
        pages = [1 for _ in queries]
        exhausted = set()
        searched = []
        requests = 0
        rng = random.SystemRandom()
        def fill(candidate_pools):
            # Round-robin selection avoids letting the first query take all slots.
            while len(chosen) < LIMIT:
                added = False
                for pool in candidate_pools:
                    while pool:
                        if take(pool.pop()):
                            added = True
                            break
                    if len(chosen) >= LIMIT: break
                if not added: break
        # Initially sample up to three closely related queries even if one is plentiful.
        # Extra pages/terms are fetched only when those cannot supply enough fresh IDs.
        initial = min(3, len(queries))
        pending = list(range(initial))
        while len(chosen) < LIMIT and requests < 10:
            if cancel is not None and Path(cancel).exists(): raise Cancelled()
            if not pending:
                pending = [i for i in range(len(queries)) if i not in exhausted]
                if not pending: break
            i = pending.pop(0)
            term = queries[i]
            update(f'Tìm Pixabay {requests+1}/10 · {term} · đã chọn {len(chosen)}/{LIMIT} video mới')
            hits = search(term, page=pages[i], ratio=ratio)
            pages[i] += 1; requests += 1
            if term not in searched: searched.append(term)
            if not hits: exhausted.add(i)
            fresh = [h for h in hits if str(int(h['id'])) not in used]
            rng.shuffle(fresh); pools[i].extend(fresh)
            if requests >= initial: fill(pools)
        if allow_partial and len(chosen) < LIMIT:
            fallback_terms = ('nature landscape', 'cloudy sky', 'flowing water',
                              'leaves in wind', 'mountain landscape', 'ocean waves',
                              'countryside', 'garden flowers', 'city skyline')
            remaining_terms = [term for term in fallback_terms if term not in searched]
            for start in range(0, len(remaining_terms), 3):
                fallback_pools = []
                for term in remaining_terms[start:start + 3]:
                    if cancel is not None and Path(cancel).exists():
                        raise Cancelled()
                    update(f'Tìm thêm nền Pixabay {ratio} · {term} · đã chọn {len(chosen)}/{LIMIT}')
                    hits = list(search(term, ratio=ratio))
                    searched.append(term)
                    requests += 1
                    rng.shuffle(hits)
                    fallback_pools.append(hits)
                fill(fallback_pools)
                if len(chosen) >= LIMIT:
                    break
        if len(chosen) < LIMIT and not allow_partial:
            raise ValueError(f'Chỉ còn {len(chosen)} video Pixabay mới theo từ khóa này; cần {LIMIT} video {ratio} không trùng phiên trước. Đã thử các chủ đề liên quan phù hợp; hãy nhập chủ đề rộng hơn rồi dựng lại.')
        if cancel is not None and Path(cancel).exists(): raise Cancelled()
        rng.shuffle(chosen)
        for hit in chosen: history[str(hit['id'])] = folder.name
        # History first: a crash can reserve unused IDs but never duplicate them.
        atomic(history_file, history)
        atomic(reservation, dict(query=query, searched_queries=searched, search_requests=requests, hits=chosen))
        update(f'Đã chọn {len(chosen)}/{LIMIT} video Pixabay qua {len(searched)} từ khóa')
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


def download(folder, selected, cancel, update, *, ratio='16:9', on_wrong_ratio=None):
    """Count distinct downloads per ratio and retain previous project assets."""
    if ratio not in RATIOS:raise ValueError('Tỷ lệ video Pixabay không hợp lệ.')
    if len(selected)>LIMIT:raise ValueError(f'Mỗi tỷ lệ tối đa {LIMIT} video Pixabay.')
    folder=Path(folder);manifest=folder/'pixabay-downloads.json'
    records=read(manifest) if manifest.exists() else {}
    if len(set(ratio_records(records, ratio))|{str(int(hit['id'])) for hit in selected})>LIMIT:
        raise ValueError(f'Dự án đã đạt giới hạn {LIMIT} video Pixabay {ratio}. Hãy dùng lại video đã tải.')
    from urllib.request import build_opener
    opener=build_opener(CDNRedirect())
    result=[]
    def reject(key, media):
        error = WrongRatio(key, ratio, media)
        if on_wrong_ratio is not None:
            on_wrong_ratio(error)

    for i,hit in enumerate(selected):
        if cancel.exists():raise Cancelled()
        key=str(int(hit['id']));existing=records.get(key)
        if existing:
            if existing.get('aspect', '16:9') != ratio:
                raise ValueError('Video Pixabay này đã được tải ở tỷ lệ khác. Hãy chọn video khác.')
            try:
                path = asset(folder, existing['file'])
            except ValueError:
                pass
            else:
                media = probe(path)
                if not matches_ratio(media, ratio):
                    reject(key, media)
                    continue
                result.append(existing['file'])
                continue
        if not matches_ratio(hit, ratio):
            raise ValueError(f'Chỉ tải video Pixabay {ratio}. Hãy tìm lại video.')
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
            media=probe(partial)
            if not media['video']:raise ValueError('Tệp Pixabay không phải video hợp lệ.')
            if not matches_ratio(media, ratio):
                reject(key, media)
                continue
            partial.replace(target)
            records[key]=dict(file=name,pageURL=hit.get('pageURL',''),user=hit.get('user',''),aspect=ratio)
            atomic(manifest,records);result.append(name)
        except (HTTPError,URLError,TimeoutError):raise ValueError('Chưa tải xong video Pixabay. Các video đã tải vẫn được giữ; có thể thử lại.') from None
        finally:
            if partial.exists():partial.unlink()
    return list(dict.fromkeys(result))

