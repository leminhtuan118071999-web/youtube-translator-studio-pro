import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch, MagicMock
from v3 import projects
from v3.speech import normalize_words, to_srt, to_ass, transcribe, check_words


class SpeechTests(unittest.TestCase):
    def test_word_times_preserve_language_and_pauses(self):
        words=normalize_words([NS(words=[NS(word=' Xin',start=.2,end=.5),NS(word=' chào.',start=.6,end=1),NS(word=' 再见。',start=2,end=2.6)])],3)
        srt=to_srt(words)
        self.assertIn('00:00:00,200 --> 00:00:01,000\nXin chào.',srt)
        self.assertIn('00:00:02,000 --> 00:00:02,600\n再见。',srt)
        ass=to_ass({'words':words},3,720,1280,48)
        self.assertIn('0:00:00.20,0:00:00.50',ass)
        self.assertIn(r'{\c&H00FFFF&} Xin',ass)
        gap=next(line for line in ass.splitlines() if '0:00:00.50,0:00:00.60' in line)
        self.assertNotIn('00FFFF',gap)
        self.assertNotIn('0:00:01.00,0:00:02.00',ass)
        self.assertNotIn('00FFFF&}',to_ass({'words':words},3,720,1280,48,False))

    def test_invalid_or_silent_recognition(self):
        with self.assertRaises(ValueError):normalize_words([],2)
        self.assertEqual(normalize_words([NS(words=[NS(word=' ',start=0,end=1)])],2,True),[])
        for words in [[dict(start=0,end=float('nan'),text='a')],[dict(start=2,end=3,text='a')]]:
            with self.assertRaises(ValueError):check_words({'words':words},2)

    def test_recognition_requests_transcription_not_translation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LMT_V3_HOME=tmp):
            p=projects.create('Speech');p.update(voice='voice.wav',asr_model='tiny')
            folder=projects.project_dir(p['id']);(folder/'assets'/'voice.wav').touch()
            run=folder/'runs'/'test';run.mkdir(parents=True);projects.atomic(run/'snapshot.json',p)
            model=MagicMock();model.transcribe.return_value=(iter([NS(words=[],end=.1),NS(words=[NS(word=' Bonjour.',start=.2,end=1.5)],end=1.5)]),NS(language='fr',language_probability=.99))
            with patch('faster_whisper.WhisperModel',return_value=model),patch('v3.speech.probe',return_value={'duration':2}):
                transcribe(run)
            kwargs=model.transcribe.call_args.kwargs
            self.assertEqual(kwargs['task'],'transcribe');self.assertIsNone(kwargs['language']);self.assertTrue(kwargs['word_timestamps'])
            data=json.loads((run/'words.json').read_text())
            self.assertEqual((data['language'],data['source_voice']),('fr','voice.wav'))
            self.assertIn('Bonjour.',(run/'captions.srt').read_text())

    def test_background_result_applies_only_to_same_voice(self):
        from v3.render_worker import recognize
        from v3.render import Cancelled
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LMT_V3_HOME=tmp):
            p=projects.create('Result');p['voice']='first.wav';projects.save(p)
            folder=projects.project_dir(p['id']);run=folder/'runs'/'apply';run.mkdir(parents=True)
            projects.atomic(run/'words.json',dict(language='vi',source_voice='first.wav',words=[dict(start=0,end=1,text=' Chào')]))
            (run/'captions.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nChào\n')
            proc=MagicMock();proc.poll.return_value=0;proc.returncode=0
            with patch('v3.render_worker.subprocess.Popen',return_value=proc):
                recognize(p,run,run/'cancel')
                saved=projects.read(folder/'project.json')
                self.assertEqual(saved['caption_language'],'vi')
                self.assertIn(saved['caption_words'],projects.referenced_assets(saved))
                saved['voice']='second.wav';projects.save(saved)
                with self.assertRaisesRegex(ValueError,'thay đổi'):recognize(p,run,run/'cancel')
                (run/'cancel').touch()
                with self.assertRaises(Cancelled):recognize(p,run,run/'cancel')
