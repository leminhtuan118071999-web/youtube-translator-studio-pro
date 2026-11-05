import json
import unittest
from movie_app.ai import generate

class RepairTests(unittest.TestCase):
    def request(self, shots, maximum=4):
        original={'action':'Anna asks, Benny replies.'}
        data={'mode':'repair','context':'Anna and Benny converse.','original':original,'maximum':maximum,'characters':[{'name':n} for n in ['Anna','Benny','Clara','David']]}
        return generate(data,lambda _:json.dumps({'shots':shots}))
    def shot(self, speaker='Anna', dialogue='Hello'):
        return dict(characters=['Anna','Benny'],speaker=speaker,dialogue=dialogue,action='Anna waits.',location='room',camera='closeup',wardrobe='coat')
    def test_two_speaker_turns(self):
        result=self.request([self.shot(),self.shot('Benny','Yes')])
        self.assertEqual([s['speaker'] for s in result['shots']],['Anna','Benny'])
        self.assertEqual(sum(s['duration'] for s in result['shots']),16)
    def test_excess_named_references_rejected(self):
        with self.assertRaises(ValueError):self.request([self.shot(dialogue='Anna Benny Clara David')])
    def test_time_budget_respected(self):
        with self.assertRaises(ValueError):self.request([self.shot(),self.shot()],maximum=1)
    def test_unknown_speaker_rejected(self):
        with self.assertRaises(ValueError):self.request([self.shot('Clara')])
if __name__=='__main__':unittest.main()
