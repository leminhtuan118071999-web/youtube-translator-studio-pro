import os
import tempfile
import unittest
from unittest.mock import patch
from v3 import projects


class StoryDefaultsTests(unittest.TestCase):
    def test_persist_and_inherit_without_copying_assets_or_changing_old_project(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            old=projects.create('Old')
            defaults=projects.story_defaults()
            self.assertEqual(defaults['image_edge_softness'],'off')
            self.assertFalse(defaults['snow_overlay'])
            prefs=dict(defaults,width=60,x=20,y=80,image_edge_softness='medium',snow_overlay=True,
                       auto_subtitles=False,asr_model='base',remove_background=False,
                       auto_pixabay=False,export_include_assets=False)
            projects.save_story_defaults(dict(prefs,no_intro=True,image='private.png',keep_boxes=[[0,0,50,50]]))
            self.assertEqual(projects.story_defaults(),prefs)
            new=projects.create('New')
            self.assertEqual(projects.story_defaults(),prefs)
            self.assertFalse(new['export_include_assets'])
            self.assertNotIn('image',projects.story_defaults())
            self.assertNotIn('keep_boxes',projects.story_defaults())
            saved=projects.read(projects.project_dir(old['id'])/'project.json')
            self.assertEqual(saved,old)

    def test_invalid_values_preserve_saved_preferences(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            prefs=projects.story_defaults();projects.save_story_defaults(prefs)
            for change in [dict(width=9),dict(x=101),dict(y=float('nan')),
                           dict(auto_subtitles='false'),dict(asr_model='unknown'),
                           dict(image_edge_softness='unknown'),dict(snow_overlay='true')]:
                with self.assertRaises(ValueError):projects.save_story_defaults(dict(prefs,**change))
            self.assertEqual(projects.story_defaults(),prefs)
