import json
import unittest
from movie_app.ai import generate

class VerificationTests(unittest.TestCase):
    def verify(self,quote,attribution='explicit'):
        source='Anna listens. Benny says he will leave now.'
        data={'mode':'verify','context':source,'sourceEvidence':source,'characters':[{'name':'Anna'},{'name':'Benny'}],'shots':[{'id':'SC001','characters':['Anna','Benny'],'speaker':'Anna','dialogue':'I will leave now.'}]}
        review={'id':'SC001','status':'corrected','speaker':'Benny','reason':'Benny speaks in source','evidence':'Benny says he will leave now.','source_quote':quote,'attribution':attribution}
        return generate(data,lambda _:json.dumps({'reviews':[review]}))['reviews'][0]
    def test_real_quote_supports_correction(self):
        r=self.verify('Benny says he will leave now.')
        self.assertEqual(r['verification'],'source_supported')
        self.assertEqual(r['speaker'],'Benny')
    def test_fabricated_quote_does_not_verify(self):
        r=self.verify('Benny admits he is guilty.')
        self.assertEqual(r['status'],'needs_confirmation')
        self.assertEqual(r['speaker'],'Anna')
    def test_uncertain_attribution_cannot_verify(self):
        self.assertEqual(self.verify('Anna listens.','uncertain')['verification'],'unverified')
    def test_adaptation_label_preserved(self):
        self.assertEqual(self.verify('Benny says he will leave now.','adapted')['attribution'],'adapted')
if __name__=='__main__':unittest.main()
