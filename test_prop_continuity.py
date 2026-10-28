import unittest
from wardrobe_lock import wardrobe_instruction
from video_scene_planner import batch_prompt
from repair_memory import RepairMemory

class PropContinuityTests(unittest.TestCase):
    def test_old_reference_cannot_force_backpack_back_on(self):
        prompt = wardrobe_instruction({'wardrobe_reference': 'Quỳnh Anh: white blouse, navy backpack.'})
        self.assertIn('PROP CONTINUITY OVERRIDES THIS LOCK', prompt)
        self.assertIn('even when listed in the locked reference', prompt)
        self.assertIn('Retrieving an item from a bag does not imply wearing it', prompt)

    def test_completed_context_supplied_to_later_batch(self):
        old={'number':4, 'voiceover':'She puts the backpack down.', 'visual_prompt':'The backpack rests on the floor.'}
        current={'number':19, 'voiceover':'She shows the drawing.', 'start_seconds':144, 'end_seconds':152}
        prompt=batch_prompt({'scenes':[old,current], 'language':'Vietnamese', 'character_bible':'Quỳnh Anh', 'character_profiles':[]},[current],style='cinematic')
        self.assertIn('The backpack rests on the floor.',prompt)
        self.assertIn('Story actions override',prompt)

    def test_verified_prop_lesson_reused(self):
        memory=RepairMemory()
        memory.observe('Both scenes restore the backpack after she sets it down.')
        memory.confirm()
        self.assertIn('Put-down bags stay down',RepairMemory(memory.encoded()).instructions())
