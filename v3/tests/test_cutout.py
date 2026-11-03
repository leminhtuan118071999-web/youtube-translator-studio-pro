"""Regression tests for combining multiple people without downloading AI weights."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from v3.story import group_cutout, cutout_signature, signature


class GroupCutoutTests(unittest.TestCase):
    def test_regional_masks_restore_both_sides_and_keep_full_frame_person(self):
        original = Image.new('RGBA', (1000, 600), (80, 90, 100, 255))
        full = Image.new('L', original.size)
        full.paste(255, (480, 100, 520, 500))
        left = Image.new('L', (650, 600))
        left.paste(255, (30, 50, 80, 550))
        right = Image.new('L', (650, 600))
        right.paste(255, (550, 50, 600, 550))
        api = SimpleNamespace(new_session=Mock(return_value=object()), remove=Mock(side_effect=[full,left,right]))
        with patch.dict(sys.modules, rembg=api):
            result = group_cutout(original)
        for x in (50,500,925):
            self.assertEqual(result.getpixel((x,300)), (80,90,100,255))
        self.assertEqual(result.getpixel((200,300))[3], 0)
        self.assertEqual(result.size, original.size)
        self.assertEqual(api.new_session.call_count, 1)
        self.assertTrue(all(c.kwargs['only_mask'] for c in api.remove.call_args_list))

    def test_existing_transparency_is_never_filled(self):
        original = Image.new('RGBA', (100,100), (10,20,30,0))
        original.putpixel((50,50),(10,20,30,128))
        api = SimpleNamespace(new_session=Mock(), remove=Mock(return_value=Image.new('L',(100,100),255)))
        with patch.dict(sys.modules, rembg=api):result = group_cutout(original)
        self.assertEqual(result.getpixel((0,0))[3],0)
        self.assertEqual(result.getpixel((50,50))[3],128)
        self.assertEqual(api.remove.call_count,1)

    def test_old_cache_is_invalidated_and_config_changes_are_tracked(self):
        cfg=dict(image='photo.jpg',remove_background=True,keep_boxes=[])
        self.assertNotEqual(cutout_signature(cfg),signature(cfg))
        self.assertNotEqual(cutout_signature(cfg),cutout_signature(dict(cfg,keep_boxes=[[1,2,3,4]])))
