import json
import sys
from types import SimpleNamespace
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch,MagicMock
from PIL import Image
from v3 import projects,pixabay
from v3.story import prepare,cutout,layout_preview,validate_start
from v3.render import probe
from v3.render_worker import launch,current
from v3.tests.test_render import command


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,LMT_V3_HOME=self.tmp.name);self.env.start()
        self.p=projects.create('Kể chuyện');self.folder=projects.project_dir(self.p['id']);self.assets=self.folder/'assets'
        command('-f','lavfi','-i','color=blue:s=320x180:r=30','-t','0.6','-an','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(self.assets/'bg.mp4'))
        for name,freq,duration in [('intro',900,.4),('main',500,.8)]:
            command('-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000','-t',str(duration),str(self.assets/(name+'.wav')))
        image=Image.new('RGBA',(100,100));image.paste((0,255,0,255),(20,20,80,80));image.save(self.assets/'person.png')
        self.p.update(voice='main.wav',story=dict(enabled=True,image='person.png',intro='intro.wav',backgrounds=['bg.mp4'],
            remove_background=False,auto_subtitles=False,width=40,x=50,y=100))
        self.p['settings'].update(resolution=720,aspect='1:1');projects.save(self.p)

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def test_real_detached_story_loops_background_orders_audio_and_exports(self):
        self.p['export_destination']=str(Path(self.tmp.name)/'output')
        run_id=launch(self.p);run=self.folder/'runs'/run_id
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            status=current(self.folder)
            if status['state'] not in ('queued','running'):break
            time.sleep(.1)
        self.assertEqual(status['state'],'completed',status)
        media=probe(run/'output.mp4');self.assertAlmostEqual(media['duration'],1.2,delta=.1)
        import subprocess
        pixels=subprocess.run(['ffmpeg','-v','error','-ss','1','-i',str(run/'output.mp4'),'-vf','format=rgb24,crop=1:1:360:650','-frames:v','1','-threads','1','-f','rawvideo','pipe:1'],capture_output=True,check=True).stdout
        self.assertGreater(pixels[1],180);self.assertLess(pixels[2],50)
        import numpy as np
        for at,frequency in [(.05,900),(.65,500)]:
            audio=subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(run/'output.mp4'),'-t','0.2','-ar','48000','-ac','1','-f','s16le','pipe:1'],capture_output=True,check=True).stdout
            samples=np.frombuffer(audio,dtype='<i2');peak=np.argmax(abs(np.fft.rfft(samples))) *48000/len(samples)
            self.assertAlmostEqual(peak,frequency,delta=15)
        exported=Path(status['details']['export_location']);bundle=projects.read(exported/'project.json')
        self.assertTrue((exported/'assets'/bundle['voice_track']).exists())
        self.assertTrue((exported/'assets'/'intro.wav').exists())
        imported=projects.import_bundle(str(exported));self.assertEqual(imported['voice'],'main.wav')
        self.assertTrue((projects.project_dir(imported['id'])/'assets'/'person.png').exists())

    def test_background_and_voice_render_without_character_image(self):
        from v3.render import render
        self.p['story'].pop('image')
        self.p['story'].pop('intro')
        # A snapshot restored from an earlier render can contain an old overlay.
        self.p['overlay_image'] = 'person.png'
        validate_start(self.p, self.tmp.name)
        run = self.folder/'runs'/'no-photo'
        run.mkdir(parents=True)
        projects.atomic(run/'snapshot.json', self.p)
        with patch('v3.story.cutout', side_effect=AssertionError('Image processing must be skipped')):
            prepare(run)
        prepared = projects.read(run/'render-project.json')
        self.assertFalse(prepared['overlay_image'])
        self.assertEqual(prepared['scenes'][0]['file'], 'bg.mp4')
        self.assertTrue(prepared['settings']['sync_voice'])
        render(prepared, self.folder, run, lambda *_: None)
        media = probe(run/'output.mp4')
        self.assertTrue(media['audio'] and media['video'])
        self.assertAlmostEqual(media['duration'], .8, delta=.1)

    def test_provided_main_srt_preserves_text_and_offsets_after_intro(self):
        (self.assets/'voice.srt').write_text(
            '1\n00:00:00,100 --> 00:00:00,600\nCiao, Ánna!\n', encoding='utf-8')
        self.p['story'].update(main_srt='voice.srt', main_srt_voice='main.wav', auto_subtitles=True)
        run = self.folder/'runs'/'provided'
        run.mkdir(parents=True)
        projects.atomic(run/'snapshot.json', self.p)

        with patch('v3.speech.transcribe') as recognize:
            prepare(run)
            prepare(run)
            recognize.assert_not_called()
        result = projects.read(run/'render-project.json')
        self.assertIsNone(result['caption_words'])
        text = (self.assets/result['captions']).read_text(encoding='utf-8')
        self.assertNotIn('Chào.', text)
        self.assertIn('00:00:00,500 --> 00:00:01,000\nCiao, Ánna!', text)
        self.assertIn('voice.srt', projects.referenced_assets(result))

    def test_subtitles_offset_and_cached_preparation(self):
        self.p['story']['auto_subtitles']=True
        run=self.folder/'runs'/'prepare';run.mkdir(parents=True);projects.atomic(run/'snapshot.json',self.p)
        def fake_transcribe(subrun,report=None):
            self.assertEqual(projects.read(subrun/'snapshot.json')['voice'], 'main.wav')
            projects.atomic(subrun/'words.json',dict(language='it',words=[dict(start=.05,end=.2,text=' Ciao.')]))
        with patch('v3.speech.transcribe',side_effect=fake_transcribe) as recognize:
            prepare(run);prepared=projects.read(run/'render-project.json');data=projects.read(self.assets/prepared['caption_words'])
            self.assertEqual(data['language'],'it');self.assertEqual([w['start'] for w in data['words']],[.45])
            self.assertEqual(recognize.call_count,1)
            prepare(run);self.assertEqual(recognize.call_count,1)
        self.assertEqual(len(layout_preview(dict(prepared,story=dict(prepared['story'],backgrounds=['bg.mp4'])),self.folder))>100,True)

    def test_download_validates_media_and_reuses_file(self):
        payload=(self.assets/'bg.mp4').read_bytes()
        response=MagicMock();response.__enter__.return_value=response
        response.geturl.return_value='https://cdn.pixabay.com/video/test.mp4'
        response.read.side_effect=[payload,b'']
        opener=MagicMock();opener.open.return_value=response
        with patch('urllib.request.build_opener',return_value=opener):
            names=pixabay.download(self.folder,[dict(id=123,width=1920,height=1080,url=response.geturl.return_value,pageURL='https://pixabay.com/videos/id-123/')],self.folder/'cancel',lambda *a:None)
            self.assertTrue(probe(self.assets/names[0])['video'])
            again=pixabay.download(self.folder,[dict(id=123)],self.folder/'cancel',lambda *a:None)
            self.assertEqual(names,again);self.assertEqual(opener.open.call_count,1)
        self.assertEqual(projects.read(self.folder/'pixabay-downloads.json')['123']['file'],names[0])

    def test_portrait_download_checks_actual_media(self):
        portrait = self.assets/'portrait-source.mp4'
        command('-f','lavfi','-i','color=blue:s=180x320:r=30','-t','0.4',
                '-c:v','libx264','-threads','1',str(portrait))
        response=MagicMock()
        response.__enter__.return_value=response
        response.geturl.return_value='https://cdn.pixabay.com/video/portrait.mp4'
        response.read.side_effect=[portrait.read_bytes(),b'',(self.assets/'bg.mp4').read_bytes(),b'']
        opener=MagicMock()
        opener.open.return_value=response
        hit=dict(id=201,width=1080,height=1920,url=response.geturl.return_value)
        with patch('urllib.request.build_opener',return_value=opener):
            files=pixabay.download(self.folder,[hit],self.folder/'cancel',lambda *a:None,ratio='9:16')
            self.assertTrue(pixabay.matches_ratio(probe(self.assets/files[0]),'9:16'))
            with self.assertRaisesRegex(ValueError,'không đúng tỷ lệ 9:16'):
                pixabay.download(self.folder,[dict(hit,id=202)],self.folder/'cancel',lambda *a:None,ratio='9:16')
        records=projects.read(self.folder/'pixabay-downloads.json')
        self.assertEqual(records['201']['aspect'],'9:16')
        self.assertNotIn('202',records)

    def test_automatic_pixabay_search_on_start_then_reuses_downloads(self):
        self.p['story'].update(backgrounds=[],auto_pixabay=True,query='forest')
        run=self.folder/'runs'/'automatic';run.mkdir(parents=True);projects.atomic(run/'snapshot.json',self.p)
        payload=(self.assets/'bg.mp4').read_bytes()
        response=MagicMock();response.__enter__.return_value=response
        response.geturl.return_value='https://cdn.pixabay.com/video/test.mp4';response.read.side_effect=[payload,b'']*15
        opener=MagicMock();opener.open.return_value=response
        hits=[dict(id=i,width=1920,height=1080,url=response.geturl.return_value,pageURL=f'https://pixabay.com/videos/id-{i}/') for i in range(15)]
        with patch('v3.pixabay.search',return_value=hits) as search,patch('urllib.request.build_opener',return_value=opener):
            prepare(run)
            self.assertEqual(search.call_count,3)
            prepare(run)
            self.assertEqual(search.call_count,3);self.assertEqual(opener.open.call_count,15)
        result=projects.read(run/'render-project.json');self.assertEqual(len(result['scenes']),15)

    def test_keep_box_restores_requested_detail(self):
        api=SimpleNamespace(new_session=MagicMock(),remove=MagicMock(return_value=Image.new('L',(100,100))))
        with patch.dict(sys.modules,rembg=api):
            config=dict(image='person.png',remove_background=True,keep_boxes=[[20,20,80,80]])
            name=cutout(self.folder,config)
        with Image.open(self.assets/name) as image:
            self.assertEqual(image.size,(60,60));self.assertEqual(image.getpixel((1,1)),(0,255,0,255))


class PixabayTests(unittest.TestCase):
    def test_cap_and_reuse_persist_across_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'assets').mkdir()
            command('-f','lavfi','-i','color=blue:s=320x180:r=30','-t','0.2',
                    '-c:v','libx264','-threads','1',str(folder/'assets'/'existing.mp4'))
            records={str(i):dict(file='existing.mp4') for i in range(15)};projects.atomic(folder/'pixabay-downloads.json',records)
            with patch('urllib.request.build_opener') as network:
                self.assertEqual(pixabay.download(folder,[dict(id=1)],folder/'cancel',lambda *a:None),['existing.mp4'])
                network.return_value.open.assert_not_called()
                with self.assertRaises(ValueError):pixabay.download(folder,[dict(id=20)],folder/'cancel',lambda *a:None)
            for url in ('http://cdn.pixabay.com/a','https://evil.example/a','https://cdn.pixabay.com.evil.example/a'):
                with self.assertRaises(ValueError):pixabay.safe_url(url)

    def test_api_cache_and_key_are_not_in_project(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LMT_V3_HOME=tmp):
            pixabay.save_key('test-key')
            response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'hits':[]}).encode()
            with patch('v3.pixabay.urlopen',return_value=response) as network:
                self.assertEqual(pixabay.search('forest'),[]);self.assertEqual(pixabay.search('forest'),[])
                self.assertEqual(network.call_count,1)
            self.assertEqual((projects.home()/'pixabay-key.json').stat().st_mode & 0o777,0o600)
            p=projects.create('No secrets');self.assertNotIn('test-key',json.dumps(p))

