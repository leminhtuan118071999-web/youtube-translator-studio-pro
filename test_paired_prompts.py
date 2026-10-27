import json
import unittest
from video_scene_planner import narration_plan, apply_ai_batch, grouped_video_forms, continuous_image_prompts_text, batch_prompt, continuous_combined_forms_text
from generation_budgets import task_output_budget

class PairedPromptsTests(unittest.TestCase):
    def test_image_and_video_are_saved_and_exported_by_same_scene_number(self):
        p=narration_plan('Original narration.','English',audio_duration_seconds=8)
        p.update(paired_prompts_required=True,style='Realistic')
        raw=json.dumps({'scenes':[dict(number=1,visual_prompt='The girl opens the gate.',image_prompt='Opening frame: girl outside a closed gate.',transition_to_next='')]})
        apply_ai_batch(p,raw,[1])
        group=grouped_video_forms(p)[0]
        self.assertIn('01 |',group['content'])
        self.assertEqual(group['image_content'],'01 | Opening frame: girl outside a closed gate.')
        self.assertEqual(continuous_image_prompts_text(p),group['image_content'])
        prompt=batch_prompt(p,p['scenes'],style='Realistic')
        self.assertIn('PAIRED_SCENE_PROMPTS',prompt)
        self.assertIn('OPENING frame',prompt)
        self.assertEqual(task_output_budget(prompt),2600)
    def test_combining_scopes_still_constraints_and_keeps_video_and_speech(self):
        p=narration_plan('Giữ nguyên lời đọc.', 'Tiếng Việt', audio_duration_seconds=8)
        p['scenes'][0].update(visual_prompt='Camera tracks the girl.',image_prompt='Still frame | Negative: text overlays, motion blur')
        before=json.dumps(p,ensure_ascii=False)
        result=continuous_combined_forms_text(p)
        self.assertIn('OUTPUT: one continuous moving video clip',result)
        self.assertIn('not a separate shot or a freeze frame',result)
        self.assertIn('not to the video',result)
        self.assertIn('Camera tracks the girl.',result)
        self.assertIn('Voice: Giữ nguyên lời đọc.',result)
        self.assertEqual(json.dumps(p,ensure_ascii=False),before)
        self.assertEqual(result,grouped_video_forms(p)[0]['content'])

    def test_missing_image_is_rejected_before_changing_visual(self):
        p=narration_plan('Original narration.','English',audio_duration_seconds=8)
        p['paired_prompts_required']=True
        with self.assertRaises(ValueError):apply_ai_batch(p,json.dumps({'scenes':[dict(number=1,visual_prompt='Scene',transition_to_next='')]}),[1])
        self.assertEqual(p['scenes'][0]['visual_prompt'],'')
