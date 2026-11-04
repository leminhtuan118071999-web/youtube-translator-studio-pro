"""Regression tests for combining multiple people without downloading AI weights."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from v3.story import attached_details, group_cutout, cutout_signature, signature


class GroupCutoutTests(unittest.TestCase):
    def test_regional_masks_restore_both_sides_and_keep_full_frame_person(self):
        original = Image.new('RGBA', (1000, 600), (80, 90, 100, 255))
        full = Image.new('L', original.size)
        full.paste(255, (480, 100, 520, 500))
        left = Image.new('L', (650, 600))
        left.paste(255, (30, 50, 80, 550))
        right = Image.new('L', (650, 600))
        right.paste(255, (550, 50, 600, 550))
        api = SimpleNamespace(new_session=Mock(return_value=object()), remove=Mock(side_effect=[full,left,right,Image.new('L',original.size)]))
        with patch.dict(sys.modules, rembg=api):
            result = group_cutout(original)
        for x in (50,500,925):
            self.assertEqual(result.getpixel((x,300)), (80,90,100,255))
        self.assertEqual(result.getpixel((200,300))[3], 0)
        self.assertEqual(result.size, original.size)
        self.assertEqual(api.new_session.call_count, 2)
        self.assertTrue(all(c.kwargs['only_mask'] for c in api.remove.call_args_list))

    def test_existing_transparency_is_never_filled(self):
        original = Image.new('RGBA', (100,100), (10,20,30,0))
        original.putpixel((50,50),(10,20,30,128))
        api = SimpleNamespace(new_session=Mock(), remove=Mock(return_value=Image.new('L',(100,100),255)))
        with patch.dict(sys.modules, rembg=api):result = group_cutout(original)
        self.assertEqual(result.getpixel((0,0))[3],0)
        self.assertEqual(result.getpixel((50,50))[3],128)
        self.assertEqual(api.remove.call_count,2)

    def test_independent_mask_restores_missing_limb_and_hole_without_weak_background(self):
        original=Image.new('RGBA',(100,100),(40,60,80,255))
        full=Image.new('L',original.size)
        full.paste(255,(30,10,70,80))
        full.paste(0,(40,30,50,40))
        human=full.copy()
        human.paste(255,(40,30,50,40))
        human.paste(255,(10,20,30,30))
        human.paste(150,(0,80,100,100))
        api=SimpleNamespace(new_session=Mock(),remove=Mock(side_effect=[full,human]))
        with patch.dict(sys.modules,rembg=api):result=group_cutout(original,keep_attached_objects=False)
        self.assertEqual(result.getpixel((45,35)),(40,60,80,255))
        self.assertEqual(result.getpixel((20,25)),(40,60,80,255))
        self.assertEqual(result.getpixel((50,90))[3],0)
        self.assertEqual(api.new_session.call_args_list[1].args[0],'u2net_human_seg')

    def test_recovery_can_be_disabled_and_portrait_gets_overlapping_views(self):
        original=Image.new('RGBA',(400,800),(10,20,30,255))
        full=Image.new('L',original.size)
        upper=Image.new('L',(400,520));upper.paste(255,(30,20,60,50))
        lower=Image.new('L',(400,520));lower.paste(255,(100,450,140,500))
        api=SimpleNamespace(new_session=Mock(),remove=Mock(side_effect=[full,upper,lower]))
        with patch.dict(sys.modules,rembg=api):result=group_cutout(original,restore_missing=False,keep_attached_objects=False)
        self.assertEqual(result.getpixel((40,30))[3],255)
        self.assertEqual(result.getpixel((110,750))[3],255)
        self.assertEqual(api.new_session.call_count,1)

    def test_attached_object_is_kept_but_distant_object_is_not_added(self):
        person=Image.new('L',(100,100));person.paste(255,(40,10,60,85))
        candidate=person.copy()
        candidate.paste(255,(55,35,85,55))
        candidate.paste(255,(3,3,15,15))
        result=attached_details(candidate,person)
        self.assertEqual(result.getpixel((75,45)),255)
        self.assertEqual(result.getpixel((8,8)),0)
        self.assertEqual(result.getpixel((95,95)),0)

    def test_focused_prediction_restores_held_object_with_original_colors(self):
        original=Image.new('RGBA',(100,100),(21,43,65,255))
        person=Image.new('L',(100,100));person.paste(255,(40,20,60,80))
        def remove(image,**kwargs):
            if image.size==(100,100):return person.copy()
            # Person crop is x32..68,y11..89. The held item extends right.
            mask=Image.new('L',image.size)
            mask.paste(255,(8,9,28,69))
            mask.paste(255,(26,25,35,40))
            return mask
        api=SimpleNamespace(new_session=Mock(),remove=Mock(side_effect=remove))
        with patch.dict(sys.modules,rembg=api):result=group_cutout(original)
        self.assertEqual(result.getpixel((65,40)),(21,43,65,255))
        self.assertEqual(result.getpixel((10,10))[3],0)
        self.assertEqual(api.remove.call_count,3)

    def test_old_cache_is_invalidated_and_config_changes_are_tracked(self):
        cfg=dict(image='photo.jpg',remove_background=True,keep_boxes=[])
        self.assertNotEqual(cutout_signature(cfg),signature(cfg))
        self.assertNotEqual(cutout_signature(cfg),cutout_signature(dict(cfg,keep_attached_objects=False)))
        self.assertNotEqual(cutout_signature(cfg),cutout_signature(dict(cfg,restore_missing=False)))
        self.assertNotEqual(cutout_signature(cfg),cutout_signature(dict(cfg,keep_boxes=[[1,2,3,4]])))
