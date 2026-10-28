import json
import unittest
from video_scene_planner import repair_speech_segments, continuous_video_forms_text

class DeliveryRepairTests(unittest.TestCase):
    def test_missing_delivery_repaired_without_changing_words(self):
        source = 'Bố đang về đây!'
        scene = {'number':7, 'voiceover':source}
        initial = [{'kind':'character','speaker':'Bố','text':source}]
        calls=[]
        def call(prompt):
            calls.append(prompt)
            self.assertIn('REQUIRED delivery', prompt)
            return json.dumps({'segments':[{'start':0,'end':len(source),'kind':'character','speaker':'Bố','delivery':'phone'}]})
        result = repair_speech_segments(scene, initial, call, before='Quỳnh Anh nghe điện thoại, bố nói:', require_delivery=True)
        self.assertEqual(len(calls),1)
        self.assertEqual(result[0]['text'],source)
        self.assertEqual(result[0]['delivery'],'phone')
        scene.update(visual_prompt='Quỳnh Anh listens silently.', speech_segments=result, transition_to_next='')
        output=continuous_video_forms_text({'scenes':[scene], 'language':'Vietnamese'})
        self.assertIn('visible listeners silent',output)

    def test_existing_delivery_avoids_extra_request(self):
        result = repair_speech_segments({'voiceover':'Hello'}, [{'kind':'character','speaker':'Lan','text':'Hello','delivery':'off_screen'}], lambda _: self.fail('unnecessary call'), require_delivery=True)
        self.assertEqual(result[0]['delivery'],'off_screen')

    def test_missing_delivery_in_repair_is_not_guessed(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            return '{"segments":[{"start":0,"end":5,"kind":"character","speaker":"Lan"}]}'
        with self.assertRaises(ValueError):
            repair_speech_segments({'voiceover':'Hello'}, [{'kind':'character','speaker':'Lan','text':'Hello'}], call, require_delivery=True)
        self.assertEqual(len(calls),2)

    def test_narrator_delivery_is_always_off_screen(self):
        for delivery in (None, "phone", "on_screen"):
            result = repair_speech_segments(
                {"voiceover": "Mẹ dặn em về nhà."},
                [{"kind": "narrator", "speaker": "narrator", "text": "Mẹ dặn em về nhà.", "delivery": delivery}],
                lambda _: self.fail("narrator requires no AI repair"), require_delivery=True,
            )
            self.assertEqual(result[0]["delivery"], "off_screen")
            self.assertEqual(result[0]["text"], "Mẹ dặn em về nhà.")
