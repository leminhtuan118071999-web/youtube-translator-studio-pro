import os
import tempfile
import unittest
from unittest.mock import patch
from v3 import projects


class OutputDefaultsTests(unittest.TestCase):
    def test_shared_settings_persist_and_new_projects_inherit_without_changing_old_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, LMT_V3_HOME=tmp):
            old = projects.create('Old')
            settings = projects.output_defaults()
            self.assertEqual((settings['aspect'], settings['resolution'], settings['fit']), ('16:9',720,'cover'))
            settings.update(aspect='1:1',font_size=32,voice_volume=0.8)
            projects.save_output_defaults(settings)
            new = projects.create('New')
            self.assertEqual(new['settings'], settings)
            self.assertEqual(projects.output_defaults(), settings)
            self.assertEqual(projects.read(projects.project_dir(old['id'])/'project.json')['settings']['aspect'], '16:9')

    def test_invalid_settings_do_not_replace_saved_defaults(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, LMT_V3_HOME=tmp):
            original = projects.output_defaults()
            projects.save_output_defaults(original)
            with self.assertRaises(ValueError):
                projects.save_output_defaults(dict(original, music_volume=float('nan')))
            self.assertEqual(projects.output_defaults(), original)


if __name__ == '__main__': unittest.main()
