import json
import unittest
from unittest.mock import patch
from background_jobs import JobProgress
from server_video_jobs import run_video_forms_job
from video_scene_planner import continuous_video_forms_text, grouped_video_forms

class FormLanguageTests(unittest.TestCase):
    def test_detects_vietnamese_when_control_still_says_polish(self):
        from translation_language import saved_translation_language
        from faithful_summary import source_hash
        text='Bà Thu ôm Quỳnh Anh.'
        snap=dict(translated=text,language='Tiếng Ba Lan',duration_seconds=8,
                  audio_hash='hash',audio_name='voice.wav',style='2D',character_bible='Reference',
                  existing_plan=None,provider='test',base_url='',model='test',api_key='key',auto_form_language=True)
        seen=[]
        def provider(snapshot,prompt):
            seen.append(prompt)
            if prompt.startswith('DETECT_TRANSLATION_LANGUAGE'): return '{"language":"Tiếng Việt"}'
            self.assertEqual(snapshot['language'],'Tiếng Việt')
            return '{"scenes":[{"number":1,"visual_prompt":"Bà Thu ôm cháu.","transition_to_next":""}]}'
        with patch('server_video_jobs._provider_call',side_effect=provider):
            result=run_video_forms_job(snap,JobProgress())
        self.assertTrue(result['ok'],result['error'])
        plan=json.loads(result['fields']['video_forms'])
        self.assertEqual(plan['language'],'Tiếng Việt')
        record=dict(translated=text,video_forms=result['fields']['video_forms'])
        self.assertEqual(saved_translation_language(record),'Tiếng Việt')
        record['translated']='Changed translation'
        self.assertIsNone(saved_translation_language(record))
        record['optimization_review_json']=json.dumps(dict(output_sha256=source_hash(record['translated']),target_language='English'))
        self.assertEqual(saved_translation_language(record),'English')

    def test_wrong_language_is_corrected_before_publish(self):
        snap=dict(translated='Bà Thu ôm Quỳnh Anh.',language='Tiếng Việt',duration_seconds=8,
                  audio_hash='hash',audio_name='voice.wav',style='2D',character_bible='Polish reference',
                  existing_plan=None,provider='test',base_url='',model='test',api_key='key',verify_form_language=True)
        checks=[]
        def provider(snapshot,prompt):
            if prompt.startswith('Translate this fixed'): return '{"character_bible":"Bà Thu và Quỳnh Anh."}'
            if prompt.startswith('Write ONLY'): return '{"scenes":[{"number":1,"visual_prompt":"Polski opis.","transition_to_next":""}]}'
            if prompt.startswith('FORM_LANGUAGE_CHECK'):
                checks.append(prompt)
                if 'Polski opis' in prompt:return '{"ok":false,"issues":["Polish instead of Vietnamese"]}'
                return '{"ok":true,"issues":[]}'
            if prompt.startswith('Correct the visual_prompt'):return '{"scenes":[{"number":1,"visual_prompt":"Bà Thu ôm cháu gái.","transition_to_next":"","speech_segments":[{"kind":"narrator","speaker":"narrator","text":"Bà Thu ôm Quỳnh Anh."}]}]}'
            self.fail(prompt[:100])
        with patch('server_video_jobs._provider_call',side_effect=provider):
            result=run_video_forms_job(snap,JobProgress())
        self.assertTrue(result['ok'],result['error'])
        plan=json.loads(result['fields']['video_forms'])
        self.assertNotIn('Polski',plan['scenes'][0]['visual_prompt'])
        self.assertEqual(plan['scenes'][0]['voiceover'],snap['translated'])
        content=continuous_video_forms_text(plan)
        self.assertIn('Lời dẫn — người kể:',content)
        self.assertIn('Phụ đề trên màn hình:',content)
        self.assertNotIn('Voice:',grouped_video_forms(plan)[0]['content'])
        self.assertEqual(len(checks),2)
