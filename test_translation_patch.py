import json
import unittest
from narration_translation import patch_translation, translate_narration

class Progress:
    def __init__(self): self.fields={}
    def partial_result(self): return dict(self.fields)
    def publish(self,k,v): self.fields[k]=v
    def update(self,*args): pass
    def check_cancelled(self): pass

class TranslationPatchTests(unittest.TestCase):
    def test_ambiguous_time_repaired_and_reviewed_after_repeated_drafts(self):
        drafts=[]; reviews=[]
        def call(prompt):
            if prompt.startswith('NARRATION_TRANSLATION_PATCH'):
                self.assertIn('must not become',prompt)
                return json.dumps({'edits':[{'find':'alle ventidue e dieci','replace':'a ventidue minuti e dieci'}]})
            if prompt.startswith('NARRATION_TRANSLATION'):
                drafts.append(prompt)
                return 'È successo alle ventidue e dieci. Lei uscì.'
            reviews.append(prompt)
            return json.dumps({'ok':len(reviews)>3,'issues':[] if len(reviews)>3 else ['Ambiguous minutes became a clock hour.'],'source_conflicts':[]})
        result=translate_narration('At 22 minutes 10 it happened. She left.','Italian',call,Progress())
        self.assertEqual(result,'È successo a ventidue minuti e dieci. Lei uscì.')
        self.assertEqual(len(drafts),3)
        self.assertEqual(len(reviews),4)

    def test_ambiguous_or_overlapping_find_is_rejected(self):
        for edits in ([{'find':'one','replace':'two'}], [{'find':'one two','replace':'x'},{'find':'two one','replace':'y'}]):
            with self.assertRaises(ValueError):
                patch_translation('one two one','original','English','issue',lambda _: json.dumps({'edits':edits}))

    def test_failed_repair_never_gets_saved_as_translation(self):
        progress=Progress()
        def call(prompt):
            if prompt.startswith('NARRATION_TRANSLATION_PATCH'):
                return '{"edits":[{"find":"wrong","replace":"still wrong"}]}'
            if prompt.startswith('NARRATION_TRANSLATION'): return 'wrong'
            return '{"ok":false,"issues":["Wrong numbers"],"source_conflicts":[]}'
        with self.assertRaises(ValueError):
            translate_narration('22 minutes','Italian',call,progress)
        self.assertNotIn('optimization_review_json',progress.fields)
        self.assertNotIn('optimization_work_json',progress.fields)
