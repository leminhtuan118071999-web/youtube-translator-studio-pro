import json
import unittest
from video_scene_planner import narration_plan, apply_ai_batch, continuous_video_forms_text

class SpeechRolesTests(unittest.TestCase):
    def plan(self):
        p=narration_plan('Bà Thu nói: “Cảm ơn cháu.” Quỳnh Anh ôm bà.', 'Tiếng Việt',audio_duration_seconds=8)
        p['speech_roles_required']=True
        return p
    def rows(self,segments):
        return json.dumps({'scenes':[dict(number=1,visual_prompt='Bà ôm cháu.',transition_to_next='',speech_segments=segments)]})
    def test_voice_speaker_subtitle_are_separate_and_exact(self):
        p=self.plan()
        segments=[dict(kind='narrator',speaker='narrator',text='Bà Thu nói:'),dict(kind='character',speaker='Bà Thu',text='“Cảm ơn cháu.”'),dict(kind='narrator',speaker='narrator',text='Quỳnh Anh ôm bà.')]
        apply_ai_batch(p,self.rows(segments),[1])
        text=continuous_video_forms_text(p)
        self.assertIn('Lời thoại — Bà Thu: “Cảm ơn cháu.”',text)
        self.assertIn('Lời dẫn — người kể: Quỳnh Anh ôm bà.',text)
        self.assertIn('Phụ đề chỉ hiển thị chữ, không đọc lại.',text)
        self.assertNotIn(' | Lời đọc:',text)
    def test_changed_words_or_unnamed_speaker_do_not_mutate_scene(self):
        for segment in [dict(kind='character',speaker='unknown',text=self.plan()['scenes'][0]['voiceover']),dict(kind='narrator',speaker='narrator',text='Invented')]:
            p=self.plan()
            with self.assertRaises(ValueError):apply_ai_batch(p,self.rows([segment]),[1])
            self.assertEqual(p['scenes'][0]['visual_prompt'],'')
