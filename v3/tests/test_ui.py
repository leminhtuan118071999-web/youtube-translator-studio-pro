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
            self.assertTrue(next(b for b in app.button if b.label=='🎙️ Nghe giọng đọc và tạo phụ đề').disabled)
            self.assertTrue(any(s.label=='Cách hiện phụ đề nhận diện' for s in app.selectbox))
            # A fresh browser session reopens the saved project from disk.
            reopened=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
            self.assertFalse(reopened.exception)
            self.assertTrue(any(h.value=='Video thử nghiệm' for h in reopened.subheader))


    def test_completed_project_can_be_saved_to_user_folder(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,LMT_V3_HOME=str(Path(temp)/'internal')):
            project=projects.create('Video hoàn thành')
            folder=projects.project_dir(project['id']);run=folder/'runs'/'done';run.mkdir(parents=True)
            projects.atomic(run/'snapshot.json',project)
            projects.atomic(run/'status.json',dict(state='completed',progress=100,stage='Hoàn thành'))
            projects.atomic(folder/'latest.json',dict(run_id='done',pid=0))
            (run/'output.mp4').write_bytes(b'video-for-copy-test')
            app=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
            self.assertFalse(app.exception)
            destination=str(Path(temp)/'My videos')
            with patch('v3.projects.choose_folder',return_value=destination):
                next(b for b in app.button if b.label=='📁 Chọn thư mục lưu trên Mac').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(next(t for t in app.text_input if t.label=='Nơi lưu').value,destination)
            next(b for b in app.button if b.label=='Lưu vào thư mục đã chọn').click().run()
            self.assertFalse(app.exception)
            exported=list(Path(destination).glob('*/project.json'))
            self.assertEqual(len(exported),1)
            self.assertTrue(exported[0].with_name('video.mp4').exists())


if __name__=='__main__':unittest.main()
