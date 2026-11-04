import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import numpy as np
from PIL import Image
from v3 import projects
from v3.thumbnail_theme import THEMES,VERSION,pixel_values,rank_scene,resolve_query,suggest
from v3.render import Cancelled


class ThumbnailThemeTests(unittest.TestCase):
    def test_ranking_returns_visual_theme_or_rejects_ambiguous_image(self):
        bank=np.eye(len(THEMES),dtype='float32')
        result=rank_scene(bank[1:2],bank)
        self.assertEqual(result['query'],'ocean beach')
        self.assertTrue(result['confident'])
        uncertain=rank_scene(np.ones((1,len(THEMES)),dtype='float32'),bank)
        self.assertFalse(uncertain['confident']);self.assertIsNone(uncertain['query'])

    def test_preprocessing_keeps_complete_thumbnail_and_handles_transparency(self):
        image=Image.new('RGBA',(600,200),(255,0,0,0));image.paste((0,255,0,255),(0,0,30,200))
        pixels=pixel_values(image)
        self.assertEqual(pixels.shape,(1,3,224,224))
        self.assertEqual(pixels.dtype,np.float32)
        self.assertTrue(np.isfinite(pixels).all())
        self.assertGreater(pixels[0,1,112,2],pixels[0,1,112,112])

    def test_cache_is_reused_but_new_image_triggers_local_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);image=folder/'photo.png';Image.new('RGB',(100,80),'blue').save(image)
            cached=dict(version=VERSION,image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),confident=True,query='ocean beach')
            projects.atomic(folder/'thumbnail-theme.json',cached)
            with patch('v3.thumbnail_theme.model_file',side_effect=AssertionError('No download')):
                self.assertEqual(suggest(image,folder),cached)
            changed=Image.new('RGB',(100,80),'green');changed.paste('white',(10,10,40,60));changed.save(image)
            model=Mock();model.run.return_value=[np.eye(len(THEMES),dtype='float32')[0:1]]
            with patch('v3.thumbnail_theme.text_features',return_value=np.eye(len(THEMES),dtype='float32')),patch('v3.thumbnail_theme.model_file',return_value='local.onnx'),patch('v3.thumbnail_theme.session',return_value=model):
                result=suggest(image,folder)
            self.assertEqual(result['query'],'forest sunlight')
            self.assertEqual(result['source_image'],'photo.png')

    def test_flat_color_image_does_not_trigger_model_download_or_invent_a_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);image=folder/'flat.png';Image.new('RGB',(100,80),'green').save(image)
            with patch('v3.thumbnail_theme.model_file',side_effect=AssertionError('No model needed')):
                result=suggest(image,folder)
            self.assertFalse(result['confident']);self.assertIsNone(result['query'])

    def test_manual_query_is_fallback_and_cancellation_is_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LMT_V3_HOME=tmp):
            p=projects.create('Theme test');folder=projects.project_dir(p['id'])
            image=folder/'assets'/'photo.png';Image.new('RGB',(10,10),'red').save(image)
            config=dict(image='photo.png',auto_theme=True,query='city night')
            with patch('v3.thumbnail_theme.suggest',return_value=dict(confident=False,query=None)):
                self.assertEqual(resolve_query(folder,config),'city night')
            with patch('v3.thumbnail_theme.suggest',side_effect=RuntimeError('offline')):
                self.assertEqual(resolve_query(folder,config),'city night')
            with patch('v3.thumbnail_theme.suggest',side_effect=Cancelled()):
                with self.assertRaises(Cancelled):resolve_query(folder,config)
            with patch('v3.thumbnail_theme.suggest',side_effect=AssertionError('Manual mode must not load models')):
                self.assertEqual(resolve_query(folder,dict(config,auto_theme=False)),'city night')
