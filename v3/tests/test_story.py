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

    def test_image_opacity_blends_video_and_preview_and_preserves_alpha(self):
        import io
        import subprocess
        from v3.render import render
        self.p['story'].update(subscribe_corner=False)
        self.p['story'].pop('intro')
        run=self.folder/'opacity-prepare'
        run.mkdir()
        projects.atomic(run/'snapshot.json',self.p)
        prepare(run)
        prepared=projects.read(run/'render-project.json')
        png=self.assets/prepared['overlay_image']
        for opacity,alpha,green in [(100,255,255),(50,255,128),(0,255,0),(50,128,64)]:
            with self.subTest(opacity=opacity,alpha=alpha):
                with Image.open(png) as opened:image=opened.convert('RGBA')
                image.putalpha(alpha)
                image.save(png)
                prepared['story']['image_opacity']=opacity
                preview=Image.open(io.BytesIO(layout_preview(prepared,self.folder))).convert('RGB')
                self.assertAlmostEqual(preview.getpixel((240,400))[1],green,delta=2)
                out=self.folder/f'opacity-{opacity}-{alpha}'
                render(prepared,self.folder,out,lambda *_:None)
                pixel=subprocess.run(
                    ['ffmpeg','-v','error','-ss','0.2','-i',str(out/'output.mp4'),
                     '-vf','format=rgb24,crop=1:1:360:600','-frames:v','1',
                     '-threads','1','-f','rawvideo','pipe:1'],
                    capture_output=True,check=True).stdout
                self.assertAlmostEqual(pixel[1],green,delta=8)
                self.assertAlmostEqual(pixel[2],255-green,delta=8)

    def test_picture_with_all_effects_finishes_after_subscribe_moves(self):
        import subprocess
        from v3.render import render
        command('-f','lavfi','-i','sine=frequency=500:sample_rate=48000',
                '-t','9',str(self.assets/'long.wav'))
        self.p.update(voice='long.wav',overlay_image='person.png',
                      subtitle_text='Kiểm tra phụ đề và hiệu ứng.')
        self.p['scenes']=[dict(id='b',name='Background',file='bg.mp4',duration=9)]
        self.p['story'].update(image_opacity=85,snow_overlay=True,subscribe_corner=True)
        out=self.folder/'all-effects'
        render(self.p,self.folder,out,lambda *_:None)
        media=probe(out/'output.mp4')
        self.assertTrue(media['video'] and media['audio'])
        self.assertAlmostEqual(media['duration'],9,delta=.15)
        # The final frames must remain decodable after the finite sticker source
        # ends; the small badge must still be visible in the top-left corner.
        pixel=subprocess.run(['ffmpeg','-v','error','-ss','8.5','-i',str(out/'output.mp4'),
            '-vf','format=rgb24,crop=1:1:120:35','-frames:v','1','-threads','1',
            '-f','rawvideo','pipe:1'],capture_output=True,check=True).stdout
        self.assertEqual(len(pixel),3)
        self.assertGreater(pixel[0],150)
        invocations=[json.loads(line)['args'] for line in (out/'ffmpeg-commands.jsonl').read_text().splitlines()]
        for args in invocations:
            for i,value in enumerate(args):
                if value=='-i':self.assertEqual(args[i-2:i],['-threads','1'])
        graph=next(args[args.index('-filter_complex')+1] for args in invocations
                   if '-filter_complex' in args and 'with_subscribe' in args[args.index('-filter_complex')+1])
        self.assertEqual(graph.count('movie='),3)
        self.assertEqual(graph.count(':dec_threads=1'),3)
        self.assertNotIn('eval=frame',graph)
        self.assertNotIn('enable=',graph)
        self.assertIn('subscribe-animation.mov',graph)

    def test_mixed_color_scenes_keep_effects_after_scene_changes(self):
        import subprocess
        from v3.render import render
        for name,matrix,color in [('hd','bt709','blue'),('sd','smpte170m','red')]:
            command('-f','lavfi','-i',f'color={color}:s=320x180:r=30','-t','1',
                '-c:v','libx264','-threads','1','-pix_fmt','yuv420p',
                '-colorspace',matrix,'-color_primaries',matrix,'-color_trc',matrix,
                str(self.assets/(name+'.mp4')))
        command('-f','lavfi','-i','sine=frequency=500:sample_rate=48000',
                '-t','9',str(self.assets/'long.wav'))
        self.p.update(voice='long.wav',overlay_image='person.png',subtitle_text='Phụ đề qua các cảnh.')
        self.p['settings']['aspect']='16:9'
        self.p['story'].update(image_opacity=84,snow_overlay=True,subscribe_corner=True)
        self.p['scenes']=[dict(id=name,name=name,file=name+'.mp4',duration=1) for name in ('hd','sd')]
        out=self.folder/'mixed-color'
        render(self.p,self.folder,out,lambda *_:None)
        self.assertAlmostEqual(probe(out/'output.mp4')['duration'],9,delta=.15)
        for i in range(2):
            info=json.loads(subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                '-show_entries','stream=color_space,color_transfer,color_primaries,color_range',
                '-of','json',str(out/f'scene-{i:04}.mp4')],capture_output=True,text=True,check=True).stdout)['streams'][0]
            self.assertEqual(info,dict(color_space='bt709',color_transfer='bt709',color_primaries='bt709',color_range='tv'))
        # Scene transitions must not consume the one-frame character or reset
        # the finite Subscribe animation. Check both well after their first EOF.
        for x,y,channel in [(640,600,1),(120,35,0)]:
            pixel=subprocess.run(['ffmpeg','-v','error','-ss','8.5','-i',str(out/'output.mp4'),
                '-vf',f'format=rgb24,crop=1:1:{x}:{y}','-frames:v','1','-threads','1',
                '-f','rawvideo','pipe:1'],capture_output=True,check=True).stdout
            self.assertEqual(len(pixel),3)
            self.assertGreater(pixel[channel],150)
        invocations=[json.loads(line)['args'] for line in (out/'ffmpeg-commands.jsonl').read_text().splitlines()]
        final=next(args for args in invocations if args[-1]=='picture.mp4')
        self.assertEqual(final[final.index('-reinit_filter:v:0')+1],'0')
        self.assertNotIn('Reconfiguring filter graph',(out/'ffmpeg.log').read_text())

    def test_portrait_pixabay_mode_exports_landscape_with_blurred_sides(self):
        import subprocess
        from v3.render import render

        command('-f','lavfi','-i','color=blue:s=180x320:r=30','-t','0.5',
                '-vf','drawbox=x=0:y=160:w=180:h=160:c=lime:t=fill',
                '-c:v','libx264','-threads','1',str(self.assets/'portrait.mp4'))
        self.p['story'].update(pixabay_aspect='9:16', backgrounds=['portrait.mp4'], subscribe_corner=False)
        self.p['story'].pop('image')
        self.p['settings']['aspect'] = '9:16'
        self.p['subtitle_text'] = 'Phụ đề màu vàng.'
        run = self.folder/'runs'/'portrait-layout'
        run.mkdir(parents=True)
        projects.atomic(run/'snapshot.json', self.p)
        prepare(run)
        effective = projects.read(run/'render-project.json')
        self.assertEqual(effective['settings']['aspect'], '16:9')
        details = render(effective, self.folder, run, lambda *_: None)
        self.assertEqual((details['width'], details['height']), (1280, 720))
        frame = subprocess.run(
            ['ffmpeg','-v','error','-ss','0.2','-i',str(run/'output.mp4'),
             '-frames:v','1','-pix_fmt','rgb24','-threads','1','-f','rawvideo','pipe:1'],
            capture_output=True, check=True,
        ).stdout
        def pixel(x,y):
            index = (y * 1280 + x) * 3
            return frame[index:index+3]
        self.assertGreater(pixel(640, 325)[2], 200)
        self.assertGreater(pixel(640, 395)[1], 200)
        _, green, blue = pixel(90, 325)
        self.assertGreater(green, 25)
        self.assertGreater(blue, 25)
        self.assertTrue(any(r > 170 and g > 170 and b < 100
                            for r,g,b in zip(frame[::3],frame[1::3],frame[2::3])))

    def test_provided_main_srt_preserves_text_offsets_after_intro_and_renders_yellow(self):
        import subprocess
        from v3.render import render

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

        render(result, self.folder, run, lambda *_: None)
        frame = subprocess.run(
            ['ffmpeg', '-v', 'error', '-ss', '0.6', '-i', str(run/'output.mp4'),
             '-frames:v', '1', '-pix_fmt', 'rgb24', '-threads', '1', '-f', 'rawvideo', 'pipe:1'],
            capture_output=True, check=True,
        ).stdout
        self.assertTrue(any(r > 170 and g > 170 and b < 100
                            for r, g, b in zip(frame[::3], frame[1::3], frame[2::3])))

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
        import subprocess
        try:
            command('-display_rotation:v:0','90','-i',str(self.assets/'bg.mp4'),'-c','copy',str(portrait))
        except subprocess.CalledProcessError:
            command('-i',str(self.assets/'bg.mp4'),'-c','copy','-metadata:s:v:0','rotate=90',str(portrait))
        wrong = self.assets/'wrong-portrait.mp4'
        command('-f','lavfi','-i','color=blue:s=540x958:r=30','-t','0.2',
                '-c:v','libx264','-threads','1',str(wrong))
        response=MagicMock()
        response.__enter__.return_value=response
        response.geturl.return_value='https://cdn.pixabay.com/video/portrait.mp4'
        response.read.side_effect=[wrong.read_bytes(),b'',portrait.read_bytes(),b'']
        opener=MagicMock()
        opener.open.return_value=response
        hit=dict(id=201,width=1080,height=1920,url=response.geturl.return_value)
        rejected = []
        with patch('urllib.request.build_opener',return_value=opener):
            files=pixabay.download(self.folder,[dict(hit,id=202),hit],self.folder/'cancel',lambda *a:None,
                                   ratio='9:16',on_wrong_ratio=rejected.append)
        self.assertEqual([error.video_id for error in rejected],[202])
        self.assertEqual(len(files),1)
        self.assertTrue(pixabay.matches_ratio(probe(self.assets/files[0]),'9:16'))
        records=projects.read(self.folder/'pixabay-downloads.json')
        self.assertEqual(records['201']['aspect'],'9:16')
        self.assertNotIn('202',records)

    def test_preparation_skips_wrong_ratio_saved_pixabay_background(self):
        wrong = 'wrong-portrait.mp4'
        valid = 'valid-portrait.mp4'
        for name, height in ((wrong, 958), (valid, 960)):
            command('-f', 'lavfi', '-i', f'color=blue:s=540x{height}:r=30', '-t', '0.2',
                    '-c:v', 'libx264', '-threads', '1', str(self.assets/name))
        records = {'297111': dict(file=wrong, aspect='9:16'), '201': dict(file=valid, aspect='9:16')}
        projects.atomic(self.folder/'pixabay-downloads.json', records)
        self.p['story'].update(backgrounds=[wrong, valid], downloaded=records, pixabay_aspect='9:16')
        projects.save(self.p)
        run = self.folder/'runs'/'saved-backgrounds'
        run.mkdir(parents=True)
        projects.atomic(run/'snapshot.json', self.p)

        with patch('v3.pixabay.search') as search:
            prepare(run)
            prepare(run)  # A retried snapshot still contains the rejected file.
        search.assert_not_called()
        result = projects.read(run/'render-project.json')
        self.assertEqual([scene['file'] for scene in result['scenes']], [valid])
        self.assertEqual(result['settings']['aspect'], '16:9')
        self.assertEqual(projects.read(self.folder/'project.json')['story']['backgrounds'], [valid])
        self.assertEqual(projects.read(self.folder/'pixabay-downloads.json'), {'201': records['201']})

    def test_automatic_pixabay_search_on_start_then_reuses_downloads(self):
        self.p['story'].update(backgrounds=[],auto_pixabay=True,query='forest')
        run=self.folder/'runs'/'automatic';run.mkdir(parents=True);projects.atomic(run/'snapshot.json',self.p)
        payload=(self.assets/'bg.mp4').read_bytes()
        response=MagicMock();response.__enter__.return_value=response
        response.geturl.return_value='https://cdn.pixabay.com/video/test.mp4';response.read.side_effect=[payload,b'']*20
        opener=MagicMock();opener.open.return_value=response
        hits=[dict(id=i,width=1920,height=1080,url=response.geturl.return_value,pageURL=f'https://pixabay.com/videos/id-{i}/') for i in range(20)]
        with patch('v3.pixabay.search',return_value=hits) as search,patch('urllib.request.build_opener',return_value=opener):
            prepare(run)
            self.assertEqual(search.call_count,3)
            prepare(run)
            self.assertEqual(search.call_count,3);self.assertEqual(opener.open.call_count,20)
        result=projects.read(run/'render-project.json');self.assertEqual(len(result['scenes']),20)

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
            records={str(i):dict(file='existing.mp4') for i in range(20)};projects.atomic(folder/'pixabay-downloads.json',records)
            with patch('urllib.request.build_opener') as network:
                self.assertEqual(pixabay.download(folder,[dict(id=1)],folder/'cancel',lambda *a:None),['existing.mp4'])
                network.return_value.open.assert_not_called()
                with self.assertRaises(ValueError):pixabay.download(folder,[dict(id=21)],folder/'cancel',lambda *a:None)
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

