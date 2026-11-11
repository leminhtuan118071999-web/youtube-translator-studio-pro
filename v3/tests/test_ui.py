import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from v3 import projects


class EditorUITests(unittest.TestCase):
    def test_failed_render_has_resume_button_under_progress(self):
        from uuid import uuid4
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,LMT_V3_HOME=temp):
            project=projects.create('Retry project')
            folder=projects.project_dir(project['id'])
            run=folder/'runs'/uuid4().hex
            run.mkdir(parents=True)
            projects.atomic(run/'snapshot.json',project)
            projects.atomic(run/'status.json',dict(state='failed',progress=87,
                           stage='Dựng video chưa thành công',error='FFmpeg stopped'))
            projects.atomic(folder/'latest.json',dict(run_id=run.name,pid=0))
            path=str(Path(__file__).parents[1]/'studio_app.py')
            with patch('v3.render_worker.resume') as retry:
                app=AppTest.from_file(path,default_timeout=15).run()
                self.assertFalse(app.exception)
                button=next(b for b in app.button if b.label=='▶ Tiếp tục dự án')
                self.assertFalse(button.disabled)
                button.click().run()
                self.assertFalse(app.exception)
                retry.assert_called_once_with(folder,run.name)

    def test_pixabay_keywords_persist_for_new_projects_and_keep_saved_project_keywords(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,LMT_V3_HOME=folder):
            first=projects.create('First')
            path=str(Path(__file__).parents[1]/'studio_app.py')
            label='Từ khóa tìm video nền Pixabay'
            app=AppTest.from_file(path,default_timeout=15).run()
            keywords='forest sunlight, mountain lake\nautumn road'
            next(t for t in app.text_area if t.label==label).set_value(keywords).run()
            self.assertFalse(app.exception)
            self.assertEqual(projects.story_defaults()['query'],keywords)
            self.assertEqual(projects.read(projects.project_dir(first['id'])/'project.json')['story']['query'],keywords)

            projects.create('Second')
            reopened=AppTest.from_file(path,default_timeout=15).run()
            self.assertFalse(reopened.exception)
            self.assertEqual(next(t for t in reopened.text_area if t.label==label).value,keywords)
            next(t for t in reopened.text_area if t.label==label).set_value('city rain').run()
            next(b for b in reopened.button if b.label=='First').click().run()
            self.assertFalse(reopened.exception)
            self.assertEqual(next(t for t in reopened.text_area if t.label==label).value,keywords)
            self.assertEqual(projects.story_defaults()['query'],'city rain')

    def test_story_options_autosave_and_survive_new_project_and_app_restart(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,LMT_V3_HOME=folder):
            first=projects.create('First')
            path=str(Path(__file__).parents[1]/'studio_app.py')
            app=AppTest.from_file(path,default_timeout=15).run()
            next(c for c in app.checkbox if c.label=='Tạo phụ đề').uncheck().run()
            next(c for c in app.slider if c.label=='Chiều rộng nhân vật (% khung)').set_value(60).run()
            next(c for c in app.slider if c.label=='Độ hiển thị ảnh (%)').set_value(85).run()
            self.assertFalse(app.exception)
            self.assertFalse(projects.story_defaults()['auto_subtitles'])
            self.assertEqual(projects.story_defaults()['width'],60)
            self.assertEqual(projects.story_defaults()['image_opacity'],85)
            projects.create('Second')
            reopened=AppTest.from_file(path,default_timeout=15).run()
            self.assertFalse(reopened.exception)
            self.assertFalse(next(c for c in reopened.checkbox if c.label=='Tạo phụ đề').value)
            self.assertNotIn('Không dùng giọng mở đầu', [c.label for c in reopened.checkbox])
            self.assertEqual(next(c for c in reopened.slider if c.label=='Chiều rộng nhân vật (% khung)').value,60)
            self.assertEqual(next(c for c in reopened.slider if c.label=='Độ hiển thị ảnh (%)').value,85)
            self.assertNotIn('story',projects.read(projects.project_dir(first['id'])/'project.json'))

    def test_create_and_reopen_project_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,LMT_V3_HOME=folder):
            app=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
            self.assertFalse(app.exception)
            app.text_input[0].set_value('Video thử nghiệm')
            next(b for b in app.button if b.label=='＋ Tạo dự án').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(projects.listing()[0]['name'],'Video thử nghiệm')
            self.assertEqual([tab.label for tab in app.tabs],['05 · Dựng kiểu video mẫu'])
            expanders=[e.label for e in app.expander]
            self.assertLess(expanders.index('**Cấu hình xuất video**'),expanders.index('**Cài đặt tùy chỉnh**'))
            self.assertTrue(any(t.label=='Nơi lưu' for t in app.tabs[0].text_input))
            self.assertTrue(any(b.label=='🎬 Bắt đầu dựng MP4' for b in app.tabs[0].button))
            self.assertTrue(any(t.label=='05 · Dựng kiểu video mẫu' for t in app.tabs))
            next(c for c in app.checkbox if c.label=='Dựng video nền + giọng đọc').uncheck()
            next(b for b in app.button if b.label=='Lưu nguyên liệu và bố cục kể chuyện').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(projects.listing()[0]['story']['enabled'])
            self.assertTrue(any(b.label=='📁 Chọn thư mục lưu' for b in app.button))
            self.assertTrue(any(t.label=='Nơi lưu' for t in app.text_input))
            self.assertTrue(any(s.label=='Khung hình' for s in app.selectbox))
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
                next(b for b in app.button if b.label=='📁 Chọn thư mục lưu').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(next(t for t in app.text_input if t.label=='Nơi lưu').value,destination)
            next(b for b in app.button if b.label=='Lưu vào thư mục đã chọn').click().run()
            self.assertFalse(app.exception)
            exported=list(Path(destination).glob('*/project.json'))
            self.assertEqual(len(exported),1)
            self.assertTrue(exported[0].with_name('video.mp4').exists())

    def test_sidebar_project_buttons_and_confirmed_bulk_delete(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LMT_V3_HOME=tmp):
            first=projects.create('Dự án một');projects.create('Dự án hai')
            app=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
            self.assertFalse(app.exception)
            self.assertFalse(any(s.label=='Mở dự án' for s in app.selectbox))
            self.assertFalse(any(e.label=='Nhập dự án từ thư mục' for e in app.expander))
            next(b for b in app.button if b.label=='Dự án một').click().run()
            self.assertTrue(any(h.value=='Dự án một' for h in app.subheader))
            next(b for b in app.button if b.label=='Xóa tất cả phiên').click().run()
            self.assertEqual(len(projects.listing()),2)
            next(b for b in app.button if b.label=='Xác nhận xóa tất cả').click().run()
            self.assertFalse(app.exception);self.assertEqual(projects.listing(),[])
            self.assertTrue(any(t.label=='Tên dự án mới' for t in app.text_input))


if __name__=='__main__':unittest.main()

class OneClickTests(unittest.TestCase):
    def test_start_saves_current_inputs_settings_and_destination_without_save_clicks(self):
        import io
        from PIL import Image
        from v3.tests.test_render import command
        class Upload(io.BytesIO):pass
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LMT_V3_HOME=str(Path(tmp)/'projects')):
            p=projects.create('Một lần bấm')
            picture=Upload();Image.new('RGB',(80,100),'green').save(picture,format='PNG');picture.name='person.png'
            voice_path=Path(tmp)/'voice.wav';background_path=Path(tmp)/'bg.mp4'
            command('-f','lavfi','-i','sine=frequency=500:sample_rate=48000','-t','0.5',str(voice_path))
            command('-f','lavfi','-i','color=blue:s=160x120:r=30','-t','0.3','-c:v','libx264','-threads','1',str(background_path))
            voice=Upload(voice_path.read_bytes());voice.name='voice.wav'
            background=Upload(background_path.read_bytes());background.name='bg.mp4'
            captions=Upload(b'1\n00:00:00,050 --> 00:00:00,400\nCiao!\n');captions.name='voice.srt'
            def upload(label,**kwargs):
                if label.startswith('01 ·'):return picture
                if label.startswith('02 ·'):return [captions,voice]
                if label.startswith('04 ·'):return [background]
                return None
            with patch('streamlit.file_uploader',side_effect=upload),patch('v3.render_worker.launch',return_value='mock-run') as start:
                app=AppTest.from_file(str(Path(__file__).parents[1]/'studio_app.py'),default_timeout=15).run()
                self.assertFalse(app.exception)
                next(s for s in app.selectbox if s.label=='Khung hình').set_value('16:9').run()
                next(t for t in app.text_input if t.label=='Nơi lưu').set_value(str(Path(tmp)/'result')).run()
                self.assertFalse(next(b for b in app.button if b.label=='🎬 Bắt đầu dựng MP4').disabled)
                next(b for b in app.button if b.label=='🎬 Bắt đầu dựng MP4').click().run()
                self.assertFalse(app.exception);start.assert_called_once()
                snapshot=start.call_args.args[0]
                self.assertEqual(snapshot['settings']['aspect'],'16:9')
                self.assertEqual(snapshot['export_destination'],str(Path(tmp)/'result'))
                self.assertTrue(snapshot['voice']);self.assertTrue(snapshot['story']['image'])
                self.assertEqual(len(snapshot['story']['backgrounds']),1)
                self.assertEqual(snapshot['story']['main_srt_voice'],snapshot['voice'])
                self.assertTrue(snapshot['story']['main_srt'].endswith('.srt'))

