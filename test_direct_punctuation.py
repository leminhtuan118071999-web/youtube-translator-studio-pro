import json
import unittest
from direct_translation import translate_direct, END_MARKER, PUNCTUATION_RULES

class Progress:
    def __init__(self): self.fields={}
    def partial_result(self): return dict(self.fields)
    def publish(self,key,value): self.fields[key]=value
    def update(self,*args): pass
    def check_cancelled(self): pass

class PunctuationTests(unittest.TestCase):
    def test_single_call_keeps_dialogue_numbers_and_supported_ellipsis(self):
        source='Anna said: “Wait… until 06:30. The amount is 1.500 EUR.”\nBen asked: “23 minutes?”'
        calls=[];p=Progress()
        def call(prompt):
            calls.append(prompt)
            data=json.loads(prompt.split('SOURCE DATA:\n',1)[1])
            self.assertEqual(data['core'],source)
            self.assertIn(PUNCTUATION_RULES,prompt)
            return source+'\n'+END_MARKER
        self.assertEqual(translate_direct(source,'English',call,p),source)
        self.assertEqual(len(calls),1)
        self.assertEqual(translate_direct(source,'English',lambda _:self.fail('checkpoint repeated'),p),source)

    def test_existing_format_repair_also_preserves_punctuation_policy(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            if len(calls)==1:return '{"title":"wrong output"}'
            self.assertIn(PUNCTUATION_RULES,prompt)
            return 'Anna asked: “At 06:30?”\n'+END_MARKER
        self.assertEqual(translate_direct('Anna asked: “At 06:30?”','English',call,Progress()),'Anna asked: “At 06:30?”')
        self.assertEqual(len(calls),2)

    def test_complete_core_coverage_is_unchanged(self):
        source=('Anna said: “Wait 23 minutes.”\n'*400)
        cores=[]
        def call(prompt):
            core=json.loads(prompt.split('SOURCE DATA:\n',1)[1])['core']
            cores.append(core)
            return core+'\n'+END_MARKER
        result=translate_direct(source,'English',call,Progress())
        self.assertEqual(''.join(cores),source)
        self.assertEqual(result.count('23 minutes'),400)
        self.assertEqual(len(cores),3)

if __name__=='__main__': unittest.main()
