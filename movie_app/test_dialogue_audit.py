import json
import unittest
from movie_app.ai import generate

class DialogueAuditTests(unittest.TestCase):
    def run_review(self, reviews):
        shot = {'id':'SC001','characters':['Anna','Benny'],'speaker':'Anna','dialogue':'I will go.'}
        data = {'mode':'audit','context':'Benny says he will go.','characters':[{'name':'Anna'},{'name':'Benny'},{'name':'Clara'}],'shots':[shot]}
        return generate(data, lambda _: json.dumps({'reviews': reviews}))

    def review(self, **changes):
        return dict(id='SC001', status='corrected', speaker='Benny', reason='Nguồn ghi Benny nói.', evidence='Benny says he will go.', **changes)

    def test_supported_visible_speaker_correction(self):
        result = self.run_review([self.review()])
        self.assertEqual(result['reviews'][0]['speaker'], 'Benny')

    def test_absent_speaker_rejected(self):
        r=self.review();r['speaker']='Clara'
        with self.assertRaises(ValueError): self.run_review([r])

    def test_missing_review_rejected(self):
        with self.assertRaises(ValueError): self.run_review([])

    def test_missing_evidence_rejected(self):
        r=self.review();r['evidence']=''
        with self.assertRaises(ValueError): self.run_review([r])

    def test_uncertainty_preserved(self):
        r=self.review();r.update(status='needs_confirmation',speaker='Anna',evidence='',reason='Nguồn không ghi rõ người nói.')
        self.assertEqual(self.run_review([r])['reviews'][0]['status'],'needs_confirmation')

    def test_unknown_shot_rejected(self):
        r=self.review();r['id']='SC999'
        with self.assertRaises(ValueError): self.run_review([r])

if __name__=='__main__': unittest.main()
