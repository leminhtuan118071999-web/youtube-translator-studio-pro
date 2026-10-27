import json
import unittest
from faithful_summary import _review, ReviewFormatError

class ReviewRecoveryTests(unittest.TestCase):
    def test_missing_field_rechecks_same_candidate(self):
        calls = []
        def call(prompt):
            calls.append(prompt)
            return '{"ok":true,"issues":[]}' if len(calls) == 1 else '{"ok":true,"issues":[],"source_conflicts":[]}'
        self.assertEqual(_review(call, 'Nora paid 268000 USD.', 'Nora zapłaciła 268000 USD.', mode='target_rewrite',context={}), [])
        self.assertEqual(len(calls), 2)
        for prompt in calls:
            data=json.loads(prompt.split('instructions:\n')[1])
            self.assertEqual(data['candidate'], 'Nora zapłaciła 268000 USD.')

    def test_malformed_verdict_never_becomes_approval(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            return '{"ok":"true","issues":[]}'
        with self.assertRaises(ReviewFormatError):
            _review(call,'source','target',mode='target_rewrite',context={})
        self.assertEqual(len(calls),3)

    def test_factual_rejection_is_not_treated_as_format_error(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            return '{"ok":false,"issues":["Wrong actor"],"source_conflicts":[]}'
        with self.assertRaisesRegex(ValueError,'Wrong actor'):
            _review(call,'source','target',mode='target_rewrite',context={})
        self.assertEqual(len(calls),1)
