import json
import unittest
from unittest.mock import patch
from background_jobs import JobProgress, run_full_job
from direct_translation import translate_direct, parse_translation, END_MARKER
from youtube_metadata import generate_youtube_metadata

class DirectTranslationTests(unittest.TestCase):
    def test_timeout_splits_only_failed_window_and_keeps_exact_source(self):
        from api_clients import ProviderReadTimeout
        source='Anna waits 23 minutes. '*180
        progress=JobProgress();completed=[];requests=[]
        def call(prompt):
            data=json.loads(prompt.split('SOURCE DATA:\n')[1]);requests.append(data)
            if len(requests)==1:raise ProviderReadTimeout('Provider timed out')
            completed.append(data['core'])
            return json.dumps(dict(text=data['core'],complete=True,number_readings=[]))
        output=translate_direct(source,'English',call,progress,numbers_as_words=True)
        self.assertEqual(''.join(completed),source)
        self.assertTrue(all(len(core)<len(source) for core in completed))
        self.assertEqual(output,'\n\n'.join(core.strip() for core in completed))
        self.assertEqual(progress.partial_result()['tts_text'],output)
        self.assertTrue(requests[1]['after'])
        self.assertTrue(requests[2]['before'])
        self.assertTrue(requests[2]['previous'])

    def test_resume_after_child_timeout_never_repeats_completed_child(self):
        from api_clients import ProviderReadTimeout
        source='Anna tells her story. '*190
        progress=JobProgress();success=[];count=0
        def call(prompt):
            nonlocal count
            count+=1;core=json.loads(prompt.split('SOURCE DATA:\n')[1])['core']
            if count in (1,3):raise ProviderReadTimeout('Timed out')
            success.append(core)
            return core+'\n'+END_MARKER
        with self.assertRaises(ProviderReadTimeout):translate_direct(source,'English',call,progress)
        saved=json.loads(progress.partial_result()['optimization_work_json'])
        self.assertEqual(len(saved['section_texts']),1)
        first=success[0]
        def resume(prompt):
            core=json.loads(prompt.split('SOURCE DATA:\n')[1])['core']
            self.assertNotEqual(core,first)
            success.append(core)
            return core+'\n'+END_MARKER
        output=translate_direct(source,'English',resume,progress)
        self.assertEqual(''.join(success),source)
        self.assertEqual(output,'\n\n'.join(core.strip() for core in success))

    def test_short_timeout_has_no_retry_storm(self):
        from api_clients import ProviderReadTimeout
        calls=[]
        def fail(prompt):calls.append(prompt);raise ProviderReadTimeout('Unavailable')
        with self.assertRaises(ProviderReadTimeout):
            translate_direct('Short source.','English',fail,JobProgress())
        self.assertEqual(len(calls),1)

    def test_full_source_once_and_resume(self):
        source=('Anna said, "Wait 23 minutes."\n'*500)
        progress=JobProgress();cores=[]
        def call(prompt):
            self.assertTrue(prompt.startswith('DIRECT_TRANSLATION.'))
            data=json.loads(prompt.split('SOURCE DATA:\n')[1]);cores.append(data['core'])
            self.assertIn('NOT narration rewriting',prompt)
            return json.dumps(dict(text=data['core'],seo_context='Anna waits.',complete=True))
        output=translate_direct(source,'English',call,progress)
        self.assertEqual(''.join(cores),source)
        self.assertIn('"Wait 23 minutes."',output)
        self.assertEqual(translate_direct(source,'English',lambda _:self.fail('Should resume'),progress),output)
        calls=[]
        translate_direct(source,'Tiếng Việt',lambda p:(calls.append(p) or call(p)),progress)
        self.assertTrue(calls)

    def test_incomplete_part_does_not_claim_success(self):
        progress=JobProgress()
        with self.assertRaises(ValueError):
            translate_direct('Original text','English',lambda _:json.dumps(dict(text='partial',seo_context='brief',complete=False)),progress)
        self.assertNotIn('optimization_review_json',progress.partial_result())

    def test_plain_translation_no_json_required(self):
        p=JobProgress();calls=[]
        result=translate_direct('Anna said hello.','Vietnamese',lambda prompt:(calls.append(prompt) or 'Anna nói xin chào.\n'+END_MARKER),p)
        self.assertEqual(result,'Anna nói xin chào.');self.assertEqual(len(calls),1)
        self.assertNotIn('Return ONLY JSON',calls[0])

    def test_wrong_shape_repaired_once_then_kept(self):
        p=JobProgress();calls=[]
        def call(prompt):
            calls.append(prompt)
            return '{"title":"wrong output"}' if len(calls)==1 else 'Anna chào.\n'+END_MARKER
        self.assertEqual(translate_direct('Anna greets.','Vietnamese',call,p),'Anna chào.')
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[1].startswith('DIRECT_TRANSLATION_FORMAT.'))

    def test_missing_end_marker_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):parse_translation('Một phần bản dịch bị cắt')
        with self.assertRaises(ValueError):parse_translation('{"title":"SEO"}')

    def test_pending_candidate_cannot_cross_language(self):
        p=JobProgress()
        from faithful_summary import source_hash
        p.publish('optimization_work_json',json.dumps(dict(method='direct_translation_v1',source_sha256=source_hash('Source'),target_language='English',parts=[],seo_contexts=[],pending_index=0,pending_raw='Old text\n'+END_MARKER)))
        calls=[]
        result=translate_direct('Source','Vietnamese',lambda prompt:(calls.append(prompt) or 'Nguồn\n'+END_MARKER),p)
        self.assertTrue(calls);self.assertEqual(result,'Nguồn')

    def test_old_policy_checkpoint_is_not_mixed_with_new_translation(self):
        from faithful_summary import source_hash
        p=JobProgress()
        p.publish('optimization_work_json',json.dumps(dict(
            method='direct_translation_v1',source_sha256=source_hash('Source'),
            target_language='English',parts=['Old translation'],seo_contexts=[''])))
        calls=[]
        output=translate_direct('Source','English',
            lambda prompt:(calls.append(prompt) or 'New translation\n'+END_MARKER),p)
        self.assertEqual(output,'New translation')
        self.assertEqual(len(calls),1)
        self.assertEqual(json.loads(p.partial_result()['optimization_review_json'])['method'],
                         'direct_translation_v2')

    def test_fast_seo_single_call_preserves_validation(self):
        prompts=[]
        result=generate_youtube_metadata('story','original','description','English',lambda p:(prompts.append(p) or '{"title":"Title","description":"Description","tags":["story"]}'),self_check_only=True)
        self.assertEqual(len(prompts),1)
        self.assertEqual(result,('Title','Description','story'))

    def test_v2_full_flow_two_calls_no_narration_or_review(self):
        progress=JobProgress();prompts=[]
        config=dict(source='Anna said, "Wait 23 minutes."',url='',language='Tiếng Việt',title='Wait',description='',provider='API bên thứ ba (tùy chỉnh)',base_url='https://example.test/v1',model='test',api_key='SECRET',translation_mode='direct')
        def call(*args,**kwargs):
            prompt=args[4];prompts.append(prompt)
            if prompt.startswith('DIRECT_TRANSLATION.'):
                return json.dumps(dict(text='Anna nói: "Đợi 23 phút."',seo_context='Anna yêu cầu chờ 23 phút.',complete=True))
            if prompt.startswith('TARGET_METADATA.'):
                return json.dumps(dict(title='Chờ đợi',description='Anna yêu cầu chờ.',tags=['câu chuyện']))
            self.fail('Unexpected AI step: '+prompt[:50])
        with patch('background_jobs.generate_text',side_effect=call),patch('background_jobs.rewrite_target_script',side_effect=AssertionError('Narration disabled')):
            result=run_full_job(config,progress)
        self.assertTrue(result['ok'],result['error']);self.assertEqual(len(prompts),2)
        self.assertEqual(result['fields']['translated'],'Anna nói: "Đợi 23 phút."')
        self.assertEqual(result['fields']['new_title'],'Chờ đợi')
        self.assertNotIn('SECRET',str(result))
        self.assertEqual(json.loads(result['fields']['optimization_review_json'])['verification'],'model_self_check_single_pass')

if __name__=='__main__':unittest.main()

