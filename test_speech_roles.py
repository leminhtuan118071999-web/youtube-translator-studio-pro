import json
import unittest
from video_scene_planner import narration_plan, apply_ai_batch, continuous_video_forms_text, normalize_speech_segments, repair_speech_segments

class SpeechRolesTests(unittest.TestCase):
    def plan(self):
        p=narration_plan('Bà Thu nói: “Cảm ơn cháu.” Quỳnh Anh ôm bà.', 'Tiếng Việt',audio_duration_seconds=8)
        p['speech_roles_required']=True
        return p
    def rows(self,segments):
        return json.dumps({'scenes':[dict(number=1,visual_prompt='Bà ôm cháu.',transition_to_next='',speech_segments=segments)]})
    def test_invalid_role_response_is_repaired_by_exact_source_spans(self):
        text='Bà nói: “Cháu ngoan.”'
        scene={'number':1,'voiceover':text}
        calls=[]
        def call(prompt):
            calls.append(prompt)
            return json.dumps({'segments':[dict(start=0,end=8,kind='narrator',speaker='narrator'),
                dict(start=8,end=len(text),kind='character',speaker='Bà Thu')]})
        result=repair_speech_segments(scene,[{'kind':'narrator','speaker':'narrator','text':None}],call)
        self.assertEqual(''.join(x['text'] for x in result),text)
        self.assertEqual(result[1]['speaker'],'Bà Thu')
        self.assertEqual(len(calls),1)

    def test_invalid_offsets_are_bounded_and_never_accepted(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            return '{"segments":[{"start":0,"end":9999,"kind":"narrator","speaker":"narrator"}]}'
        with self.assertRaises(ValueError):repair_speech_segments({'voiceover':'Câu gốc.'},None,call)
        self.assertEqual(len(calls),2)

    def test_localized_narrator_and_uncertain_character_are_normalized(self):
        scene={'voiceover':'Bà Thu nói: “Cảm ơn cháu.”'}
        segments=[dict(kind='lời dẫn',speaker='Người kể chuyện',text='Bà Thu nói:'),
                  dict(kind='lời thoại',speaker='không rõ',text='“Cảm ơn cháu.”')]
        result=normalize_speech_segments(scene,segments)
        self.assertEqual([x['speaker'] for x in result],['narrator','narrator'])
        self.assertTrue(result[1]['speaker_uncertain'])
        self.assertEqual([x['text'] for x in result],[x['text'] for x in segments])
        self.assertEqual(segments[0]['kind'],'lời dẫn')

    def test_normalization_preserves_known_character_and_rejects_missing_words(self):
        scene={'voiceover':'“Cảm ơn cháu.”'}
        result=normalize_speech_segments(scene,[dict(kind='dialogue',speaker='Bà Thu',text=scene['voiceover'])])
        self.assertEqual(result[0]['speaker'],'Bà Thu')
        self.assertEqual(result[0]['kind'],'character')
        with self.assertRaises(ValueError):normalize_speech_segments(scene,[dict(kind='narration',speaker='',text='Changed')])

    def test_voice_speaker_subtitle_are_separate_and_exact(self):
        p=self.plan()
        segments=[dict(kind='narrator',speaker='narrator',text='Bà Thu nói:'),dict(kind='character',speaker='Bà Thu',text='“Cảm ơn cháu.”'),dict(kind='narrator',speaker='narrator',text='Quỳnh Anh ôm bà.')]
        apply_ai_batch(p,self.rows(segments),[1])
        text=continuous_video_forms_text(p)
        self.assertIn('Dialogue — Bà Thu: “Cảm ơn cháu.”',text)
        self.assertIn('Narrator (off-screen): Quỳnh Anh ôm bà.',text)
        self.assertIn('Subtitles are display-only, never read aloud again.',text)
        self.assertNotIn(' | Voice:',text)
    def test_changed_words_or_unnamed_speaker_do_not_mutate_scene(self):
        for segment in [dict(kind='character',speaker='unknown',text=self.plan()['scenes'][0]['voiceover']),dict(kind='narrator',speaker='narrator',text='Invented')]:
            p=self.plan()
            with self.assertRaises(ValueError):apply_ai_batch(p,self.rows([segment]),[1])
            self.assertEqual(p['scenes'][0]['visual_prompt'],'')
