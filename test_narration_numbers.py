import json
import unittest
from narration_translation import spell_narration_numbers, translate_narration
from test_translation_patch import Progress

class NarrationNumberTests(unittest.TestCase):
    def test_words_already_present_need_no_extra_request(self):
        self.assertEqual(spell_narration_numbers('Bà đã bảy mươi tuổi.', 'Vietnamese', lambda _: self.fail('extra request')), 'Bà đã bảy mươi tuổi.')

    def test_numeric_conversion_precedes_faithfulness_review(self):
        prompts=[]
        def call(prompt):
            prompts.append(prompt)
            if prompt.startswith('NARRATION_TRANSLATION_NUMBER_WORDS'):
                self.assertIn('no decimal digits',prompt)
                return 'Cô trả hai trăm sáu mươi tám nghìn đô la.'
            if prompt.startswith('NARRATION_TRANSLATION'):
                return 'Cô trả 268000 đô la.'
            self.assertIn('hai trăm sáu mươi tám nghìn',prompt)
            return '{"ok":true,"issues":[],"source_conflicts":[]}'
        result=translate_narration('She paid 268000 dollars.','Vietnamese',call,Progress())
        self.assertNotRegex(result,r'\d')
        self.assertEqual(len(prompts),3)

    def test_remaining_unicode_digits_rejected(self):
        for output in ('Có 12 người.', 'Có ١٢ người.', ''):
            with self.assertRaises(ValueError):
                spell_narration_numbers('Có 12 người.','Vietnamese',lambda _:output)
