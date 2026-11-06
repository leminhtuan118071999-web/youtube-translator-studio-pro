import json
import unittest
from direct_translation import translate_direct, spoken_translation, END_MARKER
from test_direct_punctuation import Progress

class NumberReadingTests(unittest.TestCase):
    def response(self,text,readings):return json.dumps(dict(text=text,complete=True,number_readings=readings),ensure_ascii=False)
    def test_one_call_keeps_canonical_text_and_builds_speech_locally(self):
        text='Anna nói: “Đợi 23 phút.” Ben hỏi: “23 phút sao?” Hẹn 06:30. Mã AX-200.'
        raw=self.response(text,[dict(number='23',occurrence=1,words='hai mươi ba'),dict(number='23',occurrence=2,words='hai mươi ba')])
        calls=[];p=Progress()
        def call(prompt):calls.append(prompt);return raw
        result=translate_direct('Source','Tiếng Việt',call,p,numbers_as_words=True)
        self.assertEqual(result,text)
        self.assertEqual(p.fields['tts_text'],text.replace('23','hai mươi ba'))
        self.assertEqual(len(calls),1)
        self.assertIn('TARGET language',calls[0])
        self.assertEqual(translate_direct('Source','Tiếng Việt',lambda _:self.fail('repeated call'),p,numbers_as_words=True),text)
    def test_ambiguous_numbers_and_identifiers_can_stay_unchanged(self):
        text='06:30; 1.500; 03/04; AX-200; 0901234567.'
        self.assertEqual(spoken_translation(self.response(text,[]),text),text)
        self.assertEqual(spoken_translation(self.response(text,[dict(number='0901234567',occurrence=1,words='phone')]),text),text)
        with self.assertRaises(ValueError):spoken_translation(self.response(text,[dict(number='200',occurrence=1,words='two hundred')]),text)
    def test_only_requested_occurrence_changes_with_exact_surrounding_prose(self):
        text='23 people at address 23. Rate: 15%.'
        actual=spoken_translation(self.response(text,[dict(number='23',occurrence=1,words='twenty-three'),dict(number='15%',occurrence=1,words='fifteen percent')]),text)
        self.assertEqual(actual,'twenty-three people at address 23. Rate: fifteen percent.')
    def test_unknown_token_duplicate_or_non_number_span_is_rejected(self):
        text='Anna waits 23 minutes.'
        for rows in [[dict(number='Anna',occurrence=1,words='Other person')],
                     [dict(number='99',occurrence=1,words='ninety-nine')],
                     [dict(number='23',occurrence=1,words='twenty-three')]*2]:
            with self.assertRaises(ValueError):spoken_translation(self.response(text,rows),text)
    def test_turning_option_on_invalidates_old_parts_without_speech(self):
        p=Progress()
        translate_direct('Source','English',lambda _:'23 minutes\n'+END_MARKER,p)
        calls=[]
        translate_direct('Source','English',lambda prompt:(calls.append(prompt) or self.response('23 minutes',[dict(number='23',occurrence=1,words='twenty-three')])),p,numbers_as_words=True)
        self.assertEqual(len(calls),1);self.assertEqual(p.fields['tts_text'],'twenty-three minutes')
    def test_bad_mapping_uses_only_existing_single_format_repair(self):
        p=Progress();calls=[]
        def call(prompt):
            calls.append(prompt)
            return self.response('23 minutes',None if len(calls)==1 else [])
        self.assertEqual(translate_direct('Source','English',call,p,numbers_as_words=True),'23 minutes')
        self.assertEqual(p.fields['tts_text'],'23 minutes');self.assertEqual(len(calls),2)
        self.assertTrue(calls[1].startswith('DIRECT_TRANSLATION_FORMAT.'))

if __name__=='__main__':unittest.main()
