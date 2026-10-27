import unittest
from video_scene_planner import add_scene_subtitles, continuous_video_forms_text, plan_export_text

class SceneSubtitleTests(unittest.TestCase):
    def test_subtitle_is_exact_voiceover_including_legacy_scenes(self):
        plan={'language':'Polish','character_bible':'', 'scenes':[
            {'number':1,'start_seconds':0,'end_seconds':8,'voiceover':'Nora płaci 268 000 USD.',
             'subtitle':'stale text','visual_prompt':'Nora płaci.', 'transition_to_next':'crossfade 1.0s'},
            {'number':2,'start_seconds':8,'end_seconds':16,'voiceover':'','visual_prompt':'Silent landscape', 'transition_to_next':''}]}
        add_scene_subtitles(plan)
        self.assertEqual(plan['scenes'][0]['subtitle'],'Nora płaci 268 000 USD.')
        self.assertEqual(plan['scenes'][1]['subtitle'],'')
        output=continuous_video_forms_text(plan)
        self.assertIn('Subtitle (on screen, target language): Nora płaci 268 000 USD.',output)
        self.assertEqual(output.count('Subtitle (on screen'),1)
        self.assertIn('Subtitle: Nora płaci 268 000 USD.',plan_export_text(plan))
