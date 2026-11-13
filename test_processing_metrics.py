import json
import unittest
from unittest.mock import patch
from background_jobs import JobProgress,metadata_for_job
from processing_metrics import ProcessingMetrics
from faithful_summary import source_hash
from narration_translation import translate_narration


class MetricsTests(unittest.TestCase):
    def test_counters_store_no_prompt_or_provider_error_and_survive_retry(self):
        p=JobProgress();m=ProcessingMetrics(p)
        with self.assertRaises(ValueError):
            m.measure('NARRATION_TRANSLATION secret source',lambda: (_ for _ in ()).throw(ValueError('secret-key')))
        m.retry_wait(3)
        m.measure('FAITHFULNESS_REVIEW private source',lambda:'accepted')
        data=p.partial_result()['processing_metrics']
        self.assertEqual((data['calls'],data['failures'],data['retries']),(2,1,1))
        self.assertEqual(data['wait_seconds'],3)
        self.assertIsNone(data['current'])
        self.assertNotIn('secret',json.dumps(data))
        self.assertNotIn('private',json.dumps(data))
        resumed=ProcessingMetrics(p)
        resumed.measure('TARGET_METADATA data',lambda:'ok')
        self.assertEqual(p.partial_result()['processing_metrics']['calls'],3)

    def test_passing_review_supplies_context_without_extra_ai_requests(self):
        source=('Nora saves Maisie. '*500).strip();calls=[];p=JobProgress()
        def call(prompt):
            calls.append(prompt)
            if prompt.startswith('NARRATION_TRANSLATION'):
                return json.loads(prompt.split('SOURCE DATA:\n')[1])['core']
            if prompt.startswith('FAITHFULNESS_REVIEW'):
                return json.dumps(dict(ok=True,issues=[],source_conflicts=[],seo_context='Nora saves Maisie.'))
            if prompt.startswith('TARGET_METADATA_REVIEW'):return '{"ok":true,"issues":[]}'
            self.assertTrue(prompt.startswith('TARGET_METADATA'))
            return '{"title":"Rescue","description":"Nora saves Maisie.","tags":["rescue"]}'
        text=translate_narration(source,'English',call,p)
        self.assertEqual(''.join(text.split()),''.join(source.split()))
        metadata_for_job(text,'','','English',call,p)
        self.assertFalse(any(c.startswith(('Summarize','Condense')) for c in calls))
        report=json.loads(p.partial_result()['optimization_review_json'])
        self.assertEqual(len(report['seo_contexts']),report['reviewed_parts'])

    def test_reviewed_narration_is_available_before_seo_and_survives_seo_failure(self):
        from background_jobs import run_full_job
        p=JobProgress()
        def provider(*args,**kwargs):
            prompt=args[4]
            if prompt.startswith('NARRATION_TRANSLATION'):return 'Reviewed narration.'
            if prompt.startswith('FAITHFULNESS_REVIEW'):return '{"ok":true,"issues":[],"source_conflicts":[]}'
            self.assertTrue(p.partial_result()['translation_complete'])
            self.assertEqual(p.partial_result()['translated'],'Reviewed narration.')
            raise RuntimeError('SEO temporarily unavailable')
        snapshot=dict(source='Original narration.',url='',language='English',provider='OpenAI',base_url='',model='test',api_key='secret')
        with patch('background_jobs.generate_text',side_effect=provider):
            result=run_full_job(snapshot,p)
        self.assertFalse(result['ok'])
        self.assertEqual(p.partial_result()['translated'],'Reviewed narration.')
        self.assertTrue(p.partial_result()['translation_complete'])
        self.assertEqual(p.partial_result()['processing_metrics']['failures'],1)

    def test_incomplete_or_stale_contexts_fall_back_to_complete_text(self):
        text='Full narration. '*600
        for contexts,hash_value in [([None],source_hash(text)),(['Old context'],'wrong hash')]:
            p=JobProgress()
            p.publish('optimization_review_json',json.dumps(dict(target_language='English',output_sha256=hash_value,reviewed_parts=1,seo_contexts=contexts)))
            with patch('background_jobs.overview',return_value='Full context') as overview,patch('background_jobs.generate_youtube_metadata',return_value=('Title','Description','Tags')):
                metadata_for_job(text,'','','English',lambda _:None,p)
                overview.assert_called_once_with(text,unittest.mock.ANY,p,context_limit=7000)
