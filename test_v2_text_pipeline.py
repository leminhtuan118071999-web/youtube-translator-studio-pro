import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'v2/backend'))
from app.text_pipeline import run_text_job
from background_jobs import JobProgress

class TextPipelineTests(unittest.TestCase):
    def test_provider_timeout_is_retryable_and_keeps_completed_metadata(self):
        from api_clients import ProviderReadTimeout
        def call(*args,**kwargs):
            if args[4].startswith('DIRECT_TRANSLATION'):raise ProviderReadTimeout('Nhà cung cấp AI phản hồi quá thời gian chờ (300 giây).')
            return '{"title":"Xin chào","description":"Lời chào.","tags":["xin chào"]}'
        with patch('app.text_pipeline.generate_text',side_effect=call):
            result=run_text_job('full',self.config(),JobProgress())
        self.assertFalse(result['ok']);self.assertTrue(result['retryable'])
        self.assertEqual(result['fields']['new_title'],'Xin chào')

    def test_mixed_temporary_and_content_error_is_not_automatically_retried(self):
        from api_clients import ProviderReadTimeout
        def call(*args,**kwargs):
            if args[4].startswith('DIRECT_TRANSLATION'):raise ProviderReadTimeout('Timed out')
            raise ValueError('Thiếu tiêu đề hoặc mô tả.')
        with patch('app.text_pipeline.generate_text',side_effect=call):
            result=run_text_job('full',self.config(),JobProgress())
        self.assertFalse(result['ok']);self.assertFalse(result['retryable'])

    def config(self):return dict(source='Anna says hello.',uploaded_source='Anna says hello.',url='',title='Hello',description='Greeting.',language='Vietnamese',provider='custom',base_url='https://example.test',model='model',api_key='SECRET')
    def test_translation_and_seo_really_overlap(self):
        translation_started=threading.Event();seo_started=threading.Event()
        def call(*args,**kwargs):
            if args[4].startswith('DIRECT_TRANSLATION'):
                translation_started.set();self.assertTrue(seo_started.wait(2),'SEO waited for translation')
                return json.dumps(dict(text='Anna nói xin chào.',seo_context='Anna chào.',complete=True,number_readings=[]))
            seo_started.set();self.assertTrue(translation_started.wait(2),'translation did not start')
            return '{"title":"Xin chào","description":"Lời chào.","tags":["xin chào"]}'
        progress=JobProgress()
        with patch('app.text_pipeline.generate_text',side_effect=call):result=run_text_job('full',self.config(),progress)
        self.assertTrue(result['ok'],result['error']);self.assertEqual(result['fields']['new_title'],'Xin chào')
        self.assertEqual(result['fields']['translated'],'Anna nói xin chào.')
        self.assertEqual(result['fields']['processing_metrics']['calls'],2)
        self.assertNotIn('SECRET',str(result))
    def test_metadata_survives_translation_failure_and_resumes_without_repeating_seo(self):
        def fail(*args,**kwargs):
            if args[4].startswith('DIRECT_TRANSLATION'):raise ValueError('bad output SECRET')
            return '{"title":"Xin chào","description":"Lời chào.","tags":["xin chào"]}'
        p=JobProgress()
        with patch('app.text_pipeline.generate_text',side_effect=fail):r=run_text_job('full',self.config(),p)
        self.assertFalse(r['ok']);self.assertEqual(r['fields']['new_title'],'Xin chào');self.assertNotIn('SECRET',r['error'])
        config=dict(self.config(),resume_fields=r['fields']);calls=[]
        def recover(*args,**kwargs):
            calls.append(args[4]);self.assertTrue(args[4].startswith('DIRECT_TRANSLATION'))
            return '{"text":"Anna nói xin chào.","seo_context":"Anna chào.","complete":true,"number_readings":[]}'
        with patch('app.text_pipeline.generate_text',side_effect=recover):result=run_text_job('full',config,JobProgress())
        self.assertTrue(result['ok'],result['error']);self.assertEqual(len(calls),1)
    def test_removed_jobs_never_call_provider(self):
        with patch('app.text_pipeline.generate_text') as call:
            for kind in ('forms','images','characters'):
                with self.assertRaises(ValueError):run_text_job(kind,self.config(),JobProgress())
            call.assert_not_called()
    def test_seo_only_works_without_translation(self):
        with patch('app.text_pipeline.generate_text',return_value='{"title":"Xin chào","description":"Lời chào.","tags":["xin chào"]}') as call:
            result=run_text_job('seo',self.config(),JobProgress())
        self.assertTrue(result['ok'],result['error']);self.assertEqual(call.call_count,1);self.assertNotIn('translated',result['fields'])
    def test_openai_seo_uses_full_medium_source_in_one_call(self):
        source = "Anna tells her story. " * 900
        config = dict(self.config(), provider='OpenAI', source=source, uploaded_source=source)
        with patch('app.text_pipeline.generate_text', return_value='{"title":"Xin chào","description":"Lời chào.","tags":["xin chào"]}') as call:
            result = run_text_job('seo', config, JobProgress())
        self.assertTrue(result['ok'], result['error'])
        self.assertEqual(call.call_count, 1)
        self.assertIn(source.strip(), call.call_args.args[4])

    def test_larger_seo_chunks_cover_all_source_without_truncation(self):
        from background_jobs import overview
        from faithful_summary import source_hash
        source = ''.join(f"Event {i:05d}. " for i in range(5000))
        chunks = []
        def summarize(prompt):
            chunks.append(prompt.split('\n', 1)[1])
            return 'Ordered story events.'
        overview(source, summarize, JobProgress(), context_limit=24000)
        self.assertEqual(source_hash(''.join(chunks)), source_hash(source))
        self.assertLess(len(chunks), 5)

    def test_number_readings_are_saved_with_translation_in_same_provider_call(self):
        p=JobProgress();config=self.config()
        def respond(*args,**kwargs):
            if args[4].startswith('DIRECT_TRANSLATION'):
                return json.dumps(dict(text='Anna đợi 23 phút.',complete=True,number_readings=[dict(number='23',occurrence=1,words='hai mươi ba')]))
            return '{"title":"Xin chào","description":"Lời chào.","tags":["xin chào"]}'
        with patch('app.text_pipeline.generate_text',side_effect=respond) as provider:
            result=run_text_job('full',config,p)
        self.assertTrue(result['ok'],result['error']);self.assertEqual(provider.call_count,2)
        self.assertEqual(result['fields']['translated'],'Anna đợi 23 phút.')
        self.assertEqual(result['fields']['tts_text'],'Anna đợi hai mươi ba phút.')
        config['resume_fields']=result['fields']
        with patch('app.text_pipeline.generate_text',side_effect=AssertionError('Do not repeat completed work')):
            resumed=run_text_job('full',config,JobProgress())
        self.assertTrue(resumed['ok'],resumed['error'])
        self.assertEqual(resumed['fields']['tts_text'],'Anna đợi hai mươi ba phút.')

    def test_youtube_metadata_and_subtitles_overlap_and_feed_originals_to_seo(self):
        caption_started=threading.Event();metadata_started=threading.Event()
        def captions(*args):
            caption_started.set();self.assertTrue(metadata_started.wait(2))
            return ('The original script.','English')
        def originals(vid):
            metadata_started.set();self.assertTrue(caption_started.wait(2))
            return dict(video_id=vid,title='Original title',description='Original description',tags=['original tag'],status=dict.fromkeys(['title','description','tags'],'fetched'))
        prompts=[]
        def call(*args,**kwargs):
            prompt=args[4];prompts.append(prompt)
            if prompt.startswith('DIRECT_TRANSLATION'):return '{"text":"Bản dịch.","complete":true,"number_readings":[]}'
            data=json.loads(prompt.split('SOURCE DATA:\n',1)[1])
            self.assertEqual(data['original_description'],'Original description')
            self.assertEqual(data['original_tags'],['original tag'])
            return '{"title":"Tiêu đề","description":"Mô tả","tags":["tag dịch"]}'
        config=dict(self.config(),source='',uploaded_source='',title='',description='',url='https://www.youtube.com/watch?v=S491shgHrLo')
        with patch('app.text_pipeline.fetch_subtitles',side_effect=captions),patch('app.text_pipeline.fetch_source_metadata',side_effect=originals),patch('app.text_pipeline.generate_text',side_effect=call):
            result=run_text_job('full',config,JobProgress())
        self.assertTrue(result['ok'],result['error']);self.assertEqual(len(prompts),2)
        self.assertEqual(result['fields']['description'],'Original description')
        self.assertEqual(result['fields']['source_tags'],['original tag'])
        config['resume_fields']=result['fields']
        with patch('app.text_pipeline.fetch_source_metadata',side_effect=AssertionError('must use checkpoint')),patch('app.text_pipeline.generate_text',side_effect=AssertionError('must keep completed branches')):
            resumed=run_text_job('full',config,JobProgress())
        self.assertTrue(resumed['ok'],resumed['error'])

if __name__=='__main__':unittest.main()

