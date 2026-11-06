"""Only text translation + parallel metadata. No video, images or narration jobs."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from api_clients import generate_text, RateLimitError, TransientProviderError
from background_jobs import fetch_subtitles, youtube_id, metadata_for_job
from direct_translation import translate_direct, METHOD
from faithful_summary import source_hash
from processing_metrics import phase_for
from youtube_source_metadata import fetch_source_metadata

SUPPORTED = ('full','translation','seo')

class BranchProgress:
    def __init__(self, shared, name):self.shared=shared;self.name=name
    def check_cancelled(self):
        with self.shared.lock:self.shared.progress.check_cancelled()
    def partial_result(self):
        with self.shared.lock:return self.shared.progress.partial_result()
    def publish(self, field, value):
        with self.shared.lock:self.shared.progress.publish(field,value)
    def snapshot(self):
        with self.shared.lock:return self.shared.progress.snapshot()
    def update(self,percent,stage):
        with self.shared.lock:
            self.shared.percent[self.name]=max(self.shared.percent[self.name],percent)
            self.shared.stage[self.name]=stage
            total=sum(self.shared.percent.values())/len(self.shared.percent)
            label=' | '.join(('Bản dịch' if k=='translation' else 'SEO')+': '+str(int(v))+'%' for k,v in self.shared.percent.items())
            self.shared.progress.update(10+int(total*.89),label+' · '+stage)

class Shared:
    def __init__(self,progress,names):
        self.progress=progress;self.lock=threading.RLock();self.percent=dict.fromkeys(names,0);self.stage={}
        self.started=time.monotonic();self.stats=dict(calls=0,failures=0,retries=0,wait_seconds=0,phases={},current=None)
    def metrics(self):
        self.stats['total_seconds']=round(time.monotonic()-self.started,2)
        import copy
        self.progress.publish('processing_metrics',copy.deepcopy(self.stats))
    def call(self,snapshot,prompt):
        phase=phase_for(prompt)
        for attempt in range(4):
            with self.lock:
                self.progress.check_cancelled();self.stats['calls']+=1
                row=self.stats['phases'].setdefault(phase,dict(calls=0,seconds=0));row['calls']+=1;self.metrics()
            started=time.monotonic();delay=None
            try:
                return generate_text(snapshot['provider'],snapshot['base_url'],snapshot['model'],snapshot['api_key'],prompt,
                    api_format=snapshot.get('api_format'),auth_mode=snapshot.get('auth_mode'))
            except (RateLimitError,TransientProviderError) as exc:
                with self.lock:self.stats['failures']+=1
                if attempt>=3 or (isinstance(exc,RateLimitError) and not exc.can_retry):raise
                delay=min(120,max(2,float(exc.retry_after or 5)*(attempt+1)))
            finally:
                with self.lock:row['seconds']+=time.monotonic()-started;self.metrics()
            if delay:
                start=time.monotonic()
                while time.monotonic()-start<delay:
                    with self.lock:
                        self.progress.check_cancelled();pct,_=self.progress.snapshot()
                        self.progress.update(pct,f'API giới hạn / tạm lỗi; chờ thử lại phần lỗi ({int(delay-(time.monotonic()-start))+1}s)')
                    time.sleep(max(0,min(.5,delay-(time.monotonic()-start))))
                with self.lock:self.stats['retries']+=1;self.stats['wait_seconds']+=time.monotonic()-start;self.metrics()


def run_text_job(kind,snapshot,progress):
    if kind not in SUPPORTED:raise ValueError('V2 chỉ hỗ trợ bản dịch và tiêu đề, mô tả, tag.')
    keys=[snapshot.get('api_key',''),snapshot.get('supadata_key','')]
    names=['seo'] if kind=='seo' else ['translation','seo']
    shared=Shared(progress,names)
    fields={};errors=[]
    try:
        # Restore only this immutable job's outputs; no old narration checkpoints.
        for key,value in (snapshot.get('resume_fields') or {}).items():
            if key in ('seo_originals_sha256','description','source_tags','source_metadata','tts_text','source','caption_language','title','translated','translation_complete','optimization_work_json','optimization_review_json','seo_work_json','new_title','new_description','seo_tags','metadata'):
                fields[key]=value;progress.publish(key,value)
        source=(snapshot.get('uploaded_source') or snapshot.get('source') or fields.get('source') or '').strip()
        vid=youtube_id(snapshot.get('url',''))
        metadata_source=fields.get('source_metadata')
        cached_metadata=isinstance(metadata_source,dict) and metadata_source.get('video_id')==vid
        if vid:
            progress.update(4,'Đang lấy phụ đề, tiêu đề, mô tả và tag gốc từ YouTube')
            with ThreadPoolExecutor(max_workers=2) as pool:
                metadata_future=None if cached_metadata else pool.submit(fetch_source_metadata,vid)
                subtitle_future=pool.submit(fetch_subtitles,vid,snapshot.get('supadata_key',''),progress) if not source else None
                if subtitle_future:
                    source,caption=subtitle_future.result()
                    fields['caption_language']=caption;progress.publish('caption_language',caption)
                if metadata_future:metadata_source=metadata_future.result()
            progress.check_cancelled()
        if not source or len(source)>350000:raise ValueError('Cần phụ đề hoặc văn bản gốc, tối đa 350.000 ký tự; không tự cắt nội dung.')
        fields['source']=source;progress.publish('source',source)
        metadata_source=metadata_source if isinstance(metadata_source,dict) else {}
        title=snapshot.get('title') or fields.get('title') or metadata_source.get('title') or ''
        description=snapshot.get('description') or fields.get('description') or metadata_source.get('description') or ''
        tags=fields.get('source_tags') if cached_metadata else metadata_source.get('tags',[])
        if not isinstance(tags,list):tags=[]
        for key,value in [('title',title),('description',description),('source_tags',tags)]:
            fields[key]=value;progress.publish(key,value)
        if vid:
            statuses=dict(metadata_source.get('status',{}))
            if snapshot.get('title'):statuses['title']='provided'
            if snapshot.get('description'):statuses['description']='provided'
            metadata_source=dict(metadata_source,video_id=vid,status=statuses)
            fields['source_metadata']=metadata_source;progress.publish('source_metadata',metadata_source)
        language=snapshot['language'];fields['language']=language
        def translate():
            bp=BranchProgress(shared,'translation');old=fields.get('translated');report={}
            try:report=json.loads(fields.get('optimization_review_json') or '{}')
            except (ValueError,TypeError):pass
            if not (isinstance(report,dict) and report.get('method')==METHOD and report.get('source_sha256')==source_hash(source)
                    and report.get('numbers_as_words') is True
                    and bool(fields.get('tts_text'))
                    and report.get('target_language')==language and isinstance(old,str) and old.strip() and report.get('output_sha256')==source_hash(old)):
                old=translate_direct(source,language,lambda p:shared.call(snapshot,p),bp,numbers_as_words=True)
            bp.publish('translated',old);bp.publish('translation_complete',True)
            bp.publish('optimization_work_json','');bp.update(100,'Bản dịch đã lưu')
            return dict(tts_text=bp.partial_result().get('tts_text',''),translated=old,translation_complete=True,optimization_work_json='',optimization_review_json=bp.partial_result().get('optimization_review_json',''))
        def metadata():
            bp=BranchProgress(shared,'seo')
            originals_sha=source_hash(json.dumps([title,description,tags],ensure_ascii=False))
            if (not vid or fields.get('seo_originals_sha256')==originals_sha) and all(isinstance(fields.get(key),str) and fields[key].strip() for key in ('new_title','new_description','seo_tags','metadata')):
                bp.update(100,'Đã khôi phục SEO xong từ checkpoint')
                return {key:fields[key] for key in ('new_title','new_description','seo_tags','metadata','seo_originals_sha256') if key in fields}
            # Uses ORIGINAL source independently; never waits for the translation.
            values=metadata_for_job(source,title,description,language,lambda p:shared.call(snapshot,p),bp,fast=True,
                context_limit=24000 if snapshot.get('provider') == 'OpenAI' else 7000,original_tags=tags)
            result=dict(zip(('new_title','new_description','seo_tags'),values));result['metadata']='\n\n'.join(values);result['seo_originals_sha256']=originals_sha
            for key,value in result.items():bp.publish(key,value)
            bp.update(100,'Tiêu đề, mô tả và tag đã lưu');return result
        tasks={'seo':metadata}
        if kind!='seo':tasks['translation']=translate
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures={executor.submit(fn):name for name,fn in tasks.items()}
            for future in as_completed(futures):
                try:fields.update(future.result())
                except Exception as exc:errors.append(futures[future]+': '+str(exc))
        progress.check_cancelled()
    except Exception as exc:errors.append(str(exc))
    finally:
        with shared.lock:
            partial=progress.partial_result()
            for key in ('seo_originals_sha256','tts_text','optimization_work_json','optimization_review_json','seo_work_json','translated','translation_complete','new_title','new_description','seo_tags','metadata'):
                if key in partial:fields[key]=partial[key]
            shared.metrics();fields['processing_metrics']=progress.partial_result().get('processing_metrics',{})
    error='; '.join(errors)
    for key in keys:
        if key:error=error.replace(key,'[KEY ĐÃ ẨN]')
    progress.update(100,'Hoàn thành bản dịch và SEO' if not errors else 'Có phần chưa hoàn thành; đã giữ kết quả xong và checkpoint')
    return dict(ok=not errors,fields=fields,error=error[:700])

