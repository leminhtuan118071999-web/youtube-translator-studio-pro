import copy
import unittest
from scene_visual_repair import visual_issue_numbers, repair_visuals

class VisualRepairTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'number':19,'visual_prompt':'She wears a backpack.','image_prompt':'Backpack on her shoulders.',
                    'speech_segments':[{'kind':'narrator','speaker':'narrator','delivery':'off_screen','text':'Bà ôm cháu.'}],
                    'transition_to_next':'crossfade 1.0s'},
                   {'number':20,'visual_prompt':'She smiles.','image_prompt':'She smiles.'}]
        self.issues=[{'scenes':[19], 'fields':['visual_prompt','image_prompt'], 'issue':'Backpack was put down.'}]

    def test_visual_correction_preserves_audio_transition_and_other_scenes(self):
        original=copy.deepcopy(self.rows)
        def call(prompt):
            self.assertIn('Remove ALL conflicting',prompt)
            return '{"scenes":[{"number":19,"visual_prompt":"She embraces her grandmother, without a backpack.","image_prompt":"She stands beside the bed, no backpack.","speech_segments":[],"transition_to_next":"BAD"}]}'
        result=repair_visuals(self.rows,self.issues,'She put it down in scene 4.',call)
        self.assertEqual(result[0]['speech_segments'],original[0]['speech_segments'])
        self.assertEqual(result[0]['transition_to_next'],original[0]['transition_to_next'])
        self.assertEqual(result[1],original[1])
        self.assertEqual(self.rows,original)

    def test_mixed_audio_issues_require_full_repair(self):
        issues=self.issues+[{'scene':19,'field':'speech_segments','issue':'wrong speaker'}]
        self.assertIsNone(visual_issue_numbers(issues,self.rows))

    def test_rejects_wrong_scene_numbers(self):
        with self.assertRaises(ValueError):
            repair_visuals(self.rows,self.issues,'',lambda _: '{"scenes":[{"number":22,"visual_prompt":"x","image_prompt":"y"}]}')

    def test_worker_rechecks_targeted_visual_repair(self):
        import json
        from unittest.mock import patch
        from background_jobs import JobProgress
        from server_video_jobs import run_video_forms_job
        text='Quỳnh Anh ôm bà.'
        snapshot=dict(translated=text,language='Tiếng Việt',duration_seconds=8,audio_hash='',audio_name='',
                      style='film',character_bible='Quỳnh Anh in a red dress.',existing_plan=None,
                      provider='test',base_url='',model='test',api_key='key',verify_form_language=True)
        checks=[]
        def call(snapshot,prompt):
            if prompt.startswith('Translate this fixed'):
                return '{"character_bible":"Quỳnh Anh in a red dress."}'
            if prompt.startswith('Write visual_prompt'):
                return json.dumps({'scenes':[{'number':1,'visual_prompt':'She wears a backpack.','image_prompt':'Backpack on shoulders.',
                                             'transition_to_next':'','speech_segments':[{'kind':'narrator','speaker':'narrator','text':text}]}]})
            if prompt.startswith('FORM_LANGUAGE_CHECK'):
                checks.append(prompt)
                return json.dumps({'ok':len(checks)>1,'issues':[] if len(checks)>1 else [{'scene':1,'fields':['visual_prompt','image_prompt'],'issue':'Backpack was put down.'}]})
            if prompt.startswith('REPAIR_SCENE_VISUALS_ONLY'):
                return '{"scenes":[{"number":1,"visual_prompt":"She hugs her grandmother without a backpack.","image_prompt":"She stands beside grandmother without a backpack."}]}'
            self.fail(prompt[:100])
        with patch('server_video_jobs._provider_call',side_effect=call):
            result=run_video_forms_job(snapshot,JobProgress())
        self.assertTrue(result['ok'],result['error'])
        self.assertEqual(len(checks),2)
        self.assertIn("without a backpack",checks[-1])
        scene=json.loads(result['fields']['video_forms'])['scenes'][0]
        self.assertEqual(scene['speech_segments'][0]['text'],text)
        self.assertIn('without a backpack',scene['visual_prompt'])
