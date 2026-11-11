from v3 import locking as fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from v3 import projects
from v3.render import plan, render, probe, validate_srt, estimated_srt, run_ffmpeg, cached_ffmpeg, Cancelled
from v3.render_worker import launch, current


def command(*args):
    subprocess.run(['ffmpeg','-v','error','-y','-threads','1',*args],check=True,capture_output=True)


class RealRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,LMT_V3_HOME=self.tmp.name);self.env.start()
        self.p=projects.create('Kiểm tra V3');self.folder=projects.project_dir(self.p['id'])
        assets=self.folder/'assets'
        command('-f','lavfi','-i','color=red:s=240x180','-frames:v','1','-threads','1',str(assets/'red.png'))
        command('-f','lavfi','-i','color=blue:s=320x180:r=30','-f','lavfi','-i','sine=frequency=300:sample_rate=48000','-t','1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac',str(assets/'blue.mp4'))
        for name,freq in [('voice',500),('music',900)]:
            command('-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000','-t','2.4',str(assets/(name+'.wav')))
        self.p['scenes']=[dict(id='r',name='SC1.png',file='red.png',duration=1),dict(id='b',name='SC2.mp4',file='blue.mp4',duration=1)]
        self.p['settings'].update(aspect='9:16',resolution=720,fit='cover')

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def test_real_mixed_media_voice_music_unicode_subtitles(self):
        self.p.update(voice='voice.wav',music='music.wav',subtitle_text='Bà tặng cháu bức tranh. Tình cảm gia đình.')
        self.p['settings']['transition']='fade'
        out=self.folder/'test-render';updates=[]
        result=render(self.p,self.folder,out,lambda n,s:updates.append(n))
        self.assertAlmostEqual(result['duration'],2.4,places=2)
        self.assertEqual((result['width'],result['height']),(720,1280))
        media=probe(out/'output.mp4');self.assertTrue(media['audio'] and media['video'])
        self.assertLess(abs(media['duration']-2.4),.15)
        self.assertEqual(updates[-1],100)
        self.assertIn('Bà tặng', (out/'captions.srt').read_text())
        # Inspect decoded center pixels to verify real scene order, not just file existence.
        for at,channel in [(.4,0),(1.8,2)]:
            sample=subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(out/'output.mp4'),'-vf','format=rgb24,crop=1:1:360:500','-frames:v','1','-threads','1','-f','rawvideo','pipe:1'],capture_output=True,check=True).stdout
            self.assertGreater(sample[channel],150)
            self.assertLess(sample[2 if channel==0 else 0],60)
        audio=subprocess.run(['ffmpeg','-v','error','-i',str(out/'output.mp4'),'-t','1','-f','s16le','-ac','1','pipe:1'],capture_output=True,check=True).stdout
        self.assertTrue(any(audio))

    def test_subscribe_starts_full_size_blinks_then_moves_to_corner_and_can_be_disabled(self):
        self.p['scenes'] = [dict(id='b', name='Blue', file='blue.mp4', duration=8)]
        self.p['subtitle_text'] = 'Phụ đề cùng video.'
        out = self.folder/'subscribe-render'
        render(self.p, self.folder, out, lambda *_: None)

        def sample(at, x, y):
            return subprocess.run(
                ['ffmpeg', '-v', 'error', '-ss', str(at), '-i', str(out/'output.mp4'),
                 '-vf', f'format=rgb24,crop=1:1:{x}:{y}', '-frames:v', '1',
                 '-threads', '1', '-f', 'rawvideo', 'pipe:1'],
                capture_output=True, check=True,
            ).stdout

        self.assertGreater(sample(.1, 485, 625)[0], 150)
        self.assertGreater(sample(1.5, 485, 625)[2], 180)
        self.assertGreater(sample(2.0, 485, 625)[0], 150)
        self.assertGreater(sample(6.1, 485, 625)[0], 150)
        self.assertGreater(sample(6.1, 120, 35)[2], 180)
        self.assertGreater(sample(7.7, 485, 625)[2], 180)
        self.assertGreater(sample(7.7, 120, 35)[0], 150)

        self.p['story'] = dict(subscribe_corner=False)
        out = self.folder/'subscribe-disabled'
        render(self.p, self.folder, out, lambda *_: None)
        self.assertGreater(sample(7.7, 120, 35)[2], 180)

    def test_real_word_highlight_render(self):
        from v3.speech import to_srt
        words=[dict(start=.2,end=.6,text=' Xin'),dict(start=.7,end=1.1,text=' chào.')]
        projects.atomic(self.folder/'assets'/'words.json',dict(source_voice='voice.wav',language='vi',words=words))
        (self.folder/'assets'/'speech.srt').write_text(to_srt(words),encoding='utf8')
        self.p.update(voice='voice.wav',captions='speech.srt',caption_words='words.json',captions_origin='asr')
        out=self.folder/'word-render'
        render(self.p,self.folder,out,lambda *a:None)
        self.assertTrue((out/'captions.ass').exists())
        # Yellow glyph pixels occur only while a word is spoken, not in the pause.
        counts=[]
        for at in (.4,1.6):
            pixels=subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(out/'output.mp4'),'-vf','format=rgb24,crop=720:180:0:1100','-frames:v','1','-threads','1','-f','rawvideo','pipe:1'],capture_output=True,check=True).stdout
            counts.append(sum(r>170 and g>170 and b<100 for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3])))
        self.assertGreater(counts[0],30);self.assertEqual(counts[1],0)

    def test_original_audio_and_no_voice_square_pad(self):
        self.p['settings'].update(aspect='1:1',original_volume=.7)
        result=render(self.p,self.folder,self.folder/'no-voice',lambda *a:None)
        self.assertEqual((result['width'],result['height']),(720,720))
        self.assertEqual(result['duration'],2)

    def test_validation_prevents_cutting_voice_and_bad_paths(self):
        self.p['voice']='voice.wav';self.p['settings']['sync_voice']=False
        with self.assertRaisesRegex(ValueError,'Giọng đọc dài'):plan(self.p,self.folder)
        with self.assertRaises(ValueError):projects.asset(self.folder,'../project.json')
        with self.assertRaises(ValueError):validate_srt('1\n00:00:00,000 --> 00:00:05,000\nToo long',2)
        self.assertIn('00:00:02,000',estimated_srt('Chào bạn. Hẹn gặp lại.',2))

    def test_cancel_before_render_produces_no_output(self):
        out=self.folder/'cancelled';out.mkdir();(out/'cancel').touch()
        with self.assertRaises(Cancelled):render(self.p,self.folder,out,lambda *a:None)
        self.assertFalse((out/'output.mp4').exists())

    def test_retry_reuses_completed_stages_and_copies_unfiltered_video(self):
        self.p.update(voice='voice.wav',story=dict(enabled=True,subscribe_corner=False))
        out=self.folder/'retry-fast'
        def stop_at_mux(args,*pos,**kwargs):
            if args[-1]=='output.pending.mp4':raise Cancelled()
            return run_ffmpeg(args,*pos,**kwargs)
        with patch('v3.render.run_ffmpeg',side_effect=stop_at_mux):
            with self.assertRaises(Cancelled):render(self.p,self.folder,out,lambda *_:None)
        names=['scene-0000.mp4','scene-0001.mp4','background.mp4','soundtrack.m4a']
        before={name:(out/name).stat().st_mtime_ns for name in names}
        with patch('v3.render.run_ffmpeg',wraps=run_ffmpeg) as calls:
            result=render(self.p,self.folder,out,lambda *_:None)
        self.assertEqual(calls.call_count,1)
        self.assertIn('-c',calls.call_args.args[0])
        self.assertNotIn('libx264',calls.call_args.args[0])
        self.assertFalse((out/'picture.mp4').exists())
        for name in names[:2]:self.assertEqual((out/name).stat().st_mtime_ns,before[name])
        output=probe(out/'output.mp4')
        self.assertTrue(output['video'] and output['audio'])
        self.assertLess(abs(output['duration']-result['duration']),.15)

    def test_intermediate_cache_invalidates_on_source_command_or_output_change(self):
        out=self.folder/'cache-check'
        out.mkdir()
        source=self.folder/'assets'/'blue.mp4'
        args=['-i',str(source),'-t','0.3','-an','-c:v','libx264','-threads','1','clip.mp4']
        self.assertFalse(cached_ffmpeg(args,out,out/'cancel',inputs=[source]))
        with patch('v3.render.run_ffmpeg',wraps=run_ffmpeg) as calls:
            self.assertTrue(cached_ffmpeg(args,out,out/'cancel',inputs=[source]))
            calls.assert_not_called()
            args[3]='0.4'
            self.assertFalse(cached_ffmpeg(args,out,out/'cancel',inputs=[source]))
            stat=source.stat()
            os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))
            self.assertFalse(cached_ffmpeg(args,out,out/'cancel',inputs=[source]))
            (out/'clip.mp4').write_bytes(b'incomplete')
            self.assertFalse(cached_ffmpeg(args,out,out/'cancel',inputs=[source]))
            self.assertEqual(calls.call_count,3)

    def test_stalled_export_stops_the_ffmpeg_process(self):
        out = self.folder/'stalled'
        out.mkdir()
        popen = subprocess.Popen
        processes = []

        def stalled_process(_args, **kwargs):
            process = popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
            processes.append(process)
            return process

        with patch('v3.render.subprocess.Popen', side_effect=stalled_process), \
                patch('v3.render.EXPORT_STALL_SECONDS', 0):
            with self.assertRaisesRegex(RuntimeError, 'FFmpeg đã dừng tiến độ'):
                run_ffmpeg([], out, out/'cancel', watch_output=out/'output.pending.mp4')
        self.assertIsNotNone(processes[0].poll())

    def test_detached_job_uses_snapshot_and_can_cancel_while_waiting(self):
        # Hold global renderer lock to keep the detached child predictably queued.
        with (projects.home()/'renderer.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            run_id=launch(self.p)
            with self.assertRaisesRegex(ValueError,'đang dựng'):launch(self.p)
            self.p['scenes']=[];projects.save(self.p)
            run=self.folder/'runs'/run_id
            self.assertEqual(len(projects.read(run/'snapshot.json')['scenes']),2)
            (run/'cancel').touch()
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                status=current(self.folder)
                if status['state']=='cancelled':break
                time.sleep(.1)
            self.assertEqual(status['state'],'cancelled',status)
            self.assertFalse((run/'output.mp4').exists())

    def test_detached_job_completes_without_browser(self):
        self.p['export_destination']=str(Path(self.tmp.name)/'chosen-output')
        self.p['scenes']=self.p['scenes'][:1];self.p['scenes'][0]['duration']=.3
        run_id=launch(self.p)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            status=current(self.folder)
            if status['state'] in ('completed','failed','interrupted'):break
            time.sleep(.1)
        self.assertEqual(status['state'],'completed',status)
        self.assertTrue((self.folder/'runs'/run_id/'output.mp4').exists())
        exported=Path(status['details']['export_location'])
        self.assertTrue((exported/'video.mp4').exists())
        self.assertTrue((exported/'project.json').exists())

    def test_new_project_does_not_cancel_existing_background_job(self):
        self.p['scenes']=self.p['scenes'][:1];self.p['scenes'][0]['duration']=.3
        with (projects.home()/'renderer.lock').open('a') as global_lock:
            fcntl.flock(global_lock,fcntl.LOCK_EX)
            run_id=launch(self.p)
            second=projects.create('Dự án thứ hai')
            second['subtitle_text']='Nội dung riêng';projects.save(second)
            self.assertIn(current(self.folder)['state'],('queued','running'))
            self.assertFalse((self.folder/'runs'/run_id/'cancel').exists())
            fcntl.flock(global_lock,fcntl.LOCK_UN)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            status=current(self.folder)
            if status['state'] in ('completed','failed','interrupted'):break
            time.sleep(.1)
        self.assertEqual(status['state'],'completed',status)
        self.assertEqual(projects.read(self.folder/'runs'/run_id/'snapshot.json')['name'],self.p['name'])
        self.assertEqual(projects.read(projects.project_dir(second['id'])/'project.json')['subtitle_text'],'Nội dung riêng')

    def test_bulk_delete_cancels_active_jobs_and_preserves_external_exports_and_key(self):
        from v3.render_worker import delete_all_projects,busy
        second=projects.create('Dự án khác')
        exports=Path(self.tmp.name)/'external-exports';exports.mkdir();(exports/'video.mp4').write_bytes(b'keep')
        projects.atomic(projects.home()/'pixabay-key.json',{'key':'keep-key'})
        with (projects.home()/'renderer.lock').open('a') as global_lock:
            fcntl.flock(global_lock,fcntl.LOCK_EX)
            run_id=launch(self.p)
            self.assertTrue(delete_all_projects()['waiting'])
            self.assertTrue((self.folder/'runs'/run_id/'cancel').exists())
            self.assertTrue((self.folder/'project.json').exists())
        deadline=time.monotonic()+15
        while busy(self.folder) and time.monotonic()<deadline:time.sleep(.1)
        result=delete_all_projects()
        self.assertFalse(result['waiting']);self.assertEqual(result['deleted'],2)
        self.assertEqual(projects.listing(),[])
        self.assertTrue((exports/'video.mp4').exists())
        self.assertEqual(projects.read(projects.home()/'pixabay-key.json')['key'],'keep-key')


if __name__=='__main__':unittest.main()

