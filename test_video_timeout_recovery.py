import json
import unittest
from api_clients import ProviderReadTimeout
from video_scene_planner import narration_plan, parse_json_object, InvalidFormJSON
from video_forms_ui import _generate_all_remaining

class VideoTimeoutRecoveryTests(unittest.TestCase):
    def test_large_requests_shrink_and_all_forms_are_checkpointed(self):
        plan=narration_plan('word '*150,'English',audio_duration_seconds=64)
        plan['style']='2D'; plan['character_bible']='Reference'
        sizes=[];saved=[]
        def ai(prompt):
            rows=json.loads(prompt.split('Input scenes:\n')[1]);sizes.append(len(rows))
            if len(rows)>1:raise ProviderReadTimeout('150s')
            return json.dumps({'scenes':[dict(number=rows[0]['number'],visual_prompt='Scene',transition_to_next='') ]})
        _generate_all_remaining(plan,ai,checkpoint=lambda p:saved.append(sum(bool(s['visual_prompt']) for s in p['scenes'])))
        self.assertEqual(sizes[:3],[6,3,1])
        self.assertEqual(saved,list(range(1,9)))

    def test_persistent_bad_json_reduces_batch_and_stops_at_one(self):
        plan=narration_plan('word '*100,'English',audio_duration_seconds=64)
        plan['style']='2D';plan['character_bible']=''
        sizes=[]
        def ai(prompt):
            sizes.append(len(json.loads(prompt.split('Input scenes:\n')[1])))
            return '{"scenes":['
        with self.assertRaises(InvalidFormJSON):_generate_all_remaining(plan,ai)
        self.assertEqual(sizes,[6,3,1])
        self.assertEqual(sum(bool(s['visual_prompt']) for s in plan['scenes']),0)

    def test_json_decoder_ignores_trailing_commentary_but_rejects_truncation(self):
        self.assertEqual(parse_json_object('```json\n{"scenes":[]}\n``` note {extra}', 'scenes'),{'scenes':[]})
        with self.assertRaises(InvalidFormJSON):parse_json_object('{"scenes":[', 'scenes')

    def test_single_scene_timeout_stops_without_loop_or_discarding_existing(self):
        plan=narration_plan('word '*100,'English',audio_duration_seconds=16)
        plan['style']='2D';plan['character_bible']=''
        plan['scenes'][0]['visual_prompt']='Already saved'
        calls=[]
        def ai(prompt):
            calls.append(prompt);raise ProviderReadTimeout('150s')
        with self.assertRaises(ProviderReadTimeout):_generate_all_remaining(plan,ai)
        self.assertEqual(len(calls),1)
        self.assertEqual(plan['scenes'][0]['visual_prompt'],'Already saved')
