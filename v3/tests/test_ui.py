import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from v3 import projects


class EditorUITests(unittest.TestCase):
    def test_create_and_reopen_project_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,LMT_V3_HOME=folder):
            app=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
            self.assertFalse(app.exception)
            app.text_input[0].set_value('Video thử nghiệm')
            next(b for b in app.button if b.label=='＋ Tạo dự án').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(projects.listing()[0]['name'],'Video thử nghiệm')
            self.assertEqual(len(app.tabs),4)
            self.assertTrue(any(s.label=='Khung hình' for s in app.selectbox))
            # A fresh browser session reopens the saved project from disk.
            reopened=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
            self.assertFalse(reopened.exception)
            self.assertTrue(any(h.value=='Video thử nghiệm' for h in reopened.subheader))


if __name__=='__main__':unittest.main()
