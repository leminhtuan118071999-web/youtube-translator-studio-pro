"""Content-free timing counters for AI operations; never store prompts or credentials."""
import time

LABELS = dict(translation='Dịch văn bản', review='Đối chiếu bản dịch', repair='Sửa phần lỗi',
              numbers='Chuẩn hóa số', context='Ngữ cảnh SEO', seo='Tạo SEO', seo_review='Kiểm tra SEO')


def phase_for(prompt):
    if prompt.startswith('DIRECT_TRANSLATION'):return 'translation'
    if prompt.startswith('NARRATION_TRANSLATION_PATCH'):return 'repair'
    if prompt.startswith('NARRATION_TRANSLATION_NUMBER_WORDS'):return 'numbers'
    if prompt.startswith('NARRATION_TRANSLATION'):return 'translation'
    if prompt.startswith('FAITHFULNESS_REVIEW'):return 'review'
    if prompt.startswith(('Summarize','Condense')):return 'context'
    if prompt.startswith(('TARGET_METADATA_REVIEW','TARGET_METADATA_TEXT_REVIEW')):return 'seo_review'
    return 'seo'


class ProcessingMetrics:
    def __init__(self, progress):
        self.progress=progress
        self.started=time.monotonic()
        prior=progress.partial_result().get('processing_metrics')
        self.data=dict(calls=0,failures=0,retries=0,wait_seconds=0,phases={},current=None)
        if isinstance(prior,dict):
            for key in ('calls','failures','retries','wait_seconds'):
                value=prior.get(key,0)
                if type(value) in (int,float) and value>=0:self.data[key]=value
            for key in LABELS:
                row=prior.get('phases',{}).get(key,{}) if isinstance(prior.get('phases'),dict) else {}
                if isinstance(row,dict) and all(type(row.get(k)) in (int,float) and row[k]>=0 for k in ('calls','seconds')):
                    self.data['phases'][key]=dict(calls=row['calls'],seconds=row['seconds'])
        previous=prior.get('total_seconds',0) if isinstance(prior,dict) else 0
        self.previous=previous if type(previous) in (int,float) and previous>=0 else 0

    def publish(self):
        self.data['total_seconds']=round(self.previous+time.monotonic()-self.started,2)
        # Copy nested structures: in-memory progress must not see later mutations.
        import copy
        self.progress.publish('processing_metrics',copy.deepcopy(self.data))

    def measure(self,prompt,operation):
        phase=phase_for(prompt);start=time.monotonic()
        self.data['calls']+=1
        row=self.data['phases'].setdefault(phase,dict(calls=0,seconds=0))
        row['calls']+=1
        self.data['current']=dict(phase=phase,started_at=time.time())
        self.publish()
        percent,stage=self.progress.snapshot()
        # Keep the outer part/stage label available; avoid nesting timing text.
        base=stage.split(' · AI: ',1)[0]
        self.progress.update(percent,f'{base} · AI: {LABELS[phase]} #{int(self.data["calls"])}')
        try:return operation()
        except Exception:
            self.data['failures']+=1
            raise
        finally:
            row['seconds']=round(row['seconds']+time.monotonic()-start,2)
            self.data['current']=None
            self.publish()

    def retry_wait(self,seconds):
        self.data['retries']+=1
        self.data['wait_seconds']=round(self.data['wait_seconds']+seconds,2)
        self.publish()
