import json
import unittest
from unittest.mock import patch
from background_jobs import JobProgress
from faithful_summary import source_windows
from narration_translation import translate_narration,patch_translation,NarrationQualityError


class AutoRepairTests(unittest.TestCase):
    def test_only_failed_part_is_split_and_every_fact_remains(self):
        source=('Jolie asked Cullen whether he had eaten. Cullen said he had not. '*90).strip()
        first=source_windows(source,limit=3500)[0]['core'];calls=[]
        def call(prompt):
            data=json.loads(prompt.split('SOURCE DATA:\n')[1]);core=data['core'];calls.append(core)
            return core if core==first or len(core)<=900 else 'Wrong speaker'
        def review(call,original,candidate,**kwargs):
            if candidate=='Wrong speaker':raise ValueError('Jolie asks Cullen, not Cullen asks Jolie.')
        progress=JobProgress()
        with patch('narration_translation._review',side_effect=review),patch('narration_translation.patch_translation',side_effect=lambda candidate,*a,**k:candidate):
            result=translate_narration(source,'English',call,progress)
        self.assertEqual(calls.count(first),1)
        self.assertEqual(''.join(result.split()),''.join(source.split()))
        self.assertEqual(progress.partial_result()['optimization_work_json'],'')
        self.assertNotIn('Wrong speaker',result)

    def test_patch_receives_neighboring_evidence_for_speaker_roles(self):
        def call(prompt):
            data=json.loads(prompt.split('SOURCE DATA:\n')[1])
            self.assertIn('Jolie asked',data['before']);self.assertIn('Cullen replied',data['after'])
            return json.dumps({'edits':[{'find':'Cullen asked Jolie','replace':'Jolie asked Cullen'}]})
        result=patch_translation('Cullen asked Jolie if he had eaten.','Had you eaten?','English','Wrong speaker',call,before='Jolie asked him.',after='Cullen replied no.')
        self.assertEqual(result,'Jolie asked Cullen if he had eaten.')

    def test_unverified_small_part_is_never_marked_successful(self):
        with patch('narration_translation._review',side_effect=ValueError('Wrong speaker')),patch('narration_translation.patch_translation',return_value='Wrong speaker'):
            with self.assertRaises(NarrationQualityError):translate_narration('Jolie asks Cullen a question.','English',lambda prompt:'Wrong speaker',JobProgress())
