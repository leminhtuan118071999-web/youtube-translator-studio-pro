import unittest
from review_app.engine import youtube_id, chunks, parse_srt, review
class Tests(unittest.TestCase):
    def test_source_coverage(self):
        s='a'*30005+'ENDING'; self.assertEqual(''.join(chunks(s)),s)
    def test_bad_url(self):
        with self.assertRaises(ValueError): youtube_id('https://evil.example/?v=abcdefghijk')
    def test_timing(self):
        cues=parse_srt('1\n00:00:01,500 --> 00:00:03,000\nHello\n')
        self.assertEqual(cues[0]['start'],1.5)
    def test_audit_rejects(self):
        def ai(p): return '{"ok":false,"issues":"wrong ending"}' if 'Audit review' in p else 'test'
        with self.assertRaisesRegex(ValueError,'wrong ending'): review('source','English',20,ai,{},lambda *_:None)
    def test_checkpoint_skips_accepted_calls(self):
        cp={}; calls=[]
        def ai(p):
            calls.append(p); return '{"ok":true,"issues":""}' if 'Audit review' in p else 'story'
        a=review('source','English',20,ai,cp,lambda *_:None); count=len(calls)
        self.assertEqual(review('source','English',20,ai,cp,lambda *_:None),a)
        self.assertEqual(len(calls),count)
if __name__=='__main__': unittest.main()
