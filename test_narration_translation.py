import json
import unittest
from unittest.mock import patch
from background_jobs import JobProgress, run_full_job
from faithful_summary import rewrite_target_script

class NarrationTests(unittest.TestCase):
    def test_all_original_is_translated_without_9000_limit_or_other_tasks(self):
        cores=[]
        original='Nora pays 268000 USD. Maisie survives.\n'*400
        def provider(p,b,m,k,prompt):
            if prompt.startswith('NARRATION_TRANSLATION'):
                core=json.loads(prompt.split('SOURCE DATA:\n')[1])['core'];cores.append(core)
                return core
            self.assertTrue(prompt.startswith('FAITHFULNESS_REVIEW'))
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        cfg=dict(source=original,url='',language='English',provider='OpenAI',base_url='',model='test',api_key='key')
        with patch('background_jobs.generate_text',side_effect=provider):
            result=run_full_job(cfg,JobProgress())
        self.assertTrue(result['ok'],result['error'])
        self.assertEqual(''.join(cores),original.strip())
        self.assertGreater(len(result['fields']['translated']),9000)
        self.assertNotIn('new_title',result['fields'])
        self.assertNotIn('character_profile',result['fields'])

    def test_minimal_correction_receives_candidate_original_and_error(self):
        drafts=[]
        def call(prompt):
            if prompt.startswith('NARRATION_TRANSLATION'):
                data=json.loads(prompt.split('SOURCE DATA:\n')[1]);drafts.append(data)
                return 'Wrong actor' if len(drafts)==1 else 'Nora pays 268000 USD.'
            return ('{"ok":false,"issues":["Wrong payer"],"source_conflicts":[]}' if len(drafts)==1
                    else '{"ok":true,"issues":[],"source_conflicts":[]}')
        self.assertEqual(rewrite_target_script('Nora pays 268000 USD.','English',call,JobProgress()),'Nora pays 268000 USD.')
        self.assertEqual(drafts[1]['candidate'],'Wrong actor')
        self.assertIn('Wrong payer',drafts[1]['required_corrections'])

    def test_resume_keeps_reviewed_parts(self):
        source='Nora pays.\n'*600
        progress=JobProgress();count=[0]
        def call(prompt):
            if prompt.startswith('NARRATION_TRANSLATION'):
                count[0]+=1
                if count[0]==2: raise RuntimeError('network')
                return json.loads(prompt.split('SOURCE DATA:\n')[1])['core']
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        with self.assertRaises(RuntimeError): rewrite_target_script(source,'English',call,progress)
        saved=json.loads(progress.partial_result()['optimization_work_json'])
        self.assertEqual(len(saved['parts']),1)
        seen=[]
        def resume(prompt):
            if prompt.startswith('NARRATION_TRANSLATION'):
                seen.append(prompt)
                return json.loads(prompt.split('SOURCE DATA:\n')[1])['core']
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        rewrite_target_script(source,'English',resume,progress)
        self.assertEqual(len(seen),1)
