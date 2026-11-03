import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from v3 import projects


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,LMT_V3_HOME=str(Path(self.tmp.name)/'internal'));self.env.start()
        self.project=projects.create('Dự án có dấu / thử')
        self.folder=projects.project_dir(self.project['id'])
        (self.folder/'assets'/'a.png').write_bytes(b'original-media')
        (self.folder/'assets'/'unused.png').write_bytes(b'unused')
        self.project['scenes']=[dict(file='a.png',id='a',name='Ảnh.png',duration=8)]
        self.run=self.folder/'runs'/'done';self.run.mkdir(parents=True)
        projects.atomic(self.run/'snapshot.json',self.project)
        (self.run/'output.mp4').write_bytes(b'completed-video')
        self.destination=str(Path(self.tmp.name)/'Thư mục có dấu')

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def test_full_bundle_is_portable_and_never_overwrites(self):
        a=Path(projects.export_run(self.run,self.destination));b=Path(projects.export_run(self.run,self.destination))
        self.assertNotEqual(a,b)
        self.assertEqual((a/'video.mp4').read_bytes(),b'completed-video')
        self.assertFalse((a/'assets'/'unused.png').exists())
        imported=projects.import_bundle(a)
        self.assertNotEqual(imported['id'],self.project['id'])
        self.assertEqual(imported['scenes'],self.project['scenes'])
        self.assertEqual(projects.asset(projects.project_dir(imported['id']),'a.png').read_bytes(),b'original-media')
        self.assertTrue((self.run/'output.mp4').exists())

    def test_video_only_does_not_copy_originals(self):
        exported=Path(projects.export_run(self.run,self.destination,False))
        self.assertTrue((exported/'video.mp4').exists())
        self.assertFalse((exported/'assets').exists())
        self.assertFalse((exported/'project.json').exists())

    def test_incomplete_bad_destination_and_bad_manifest_are_rejected(self):
        with self.assertRaises(ValueError):projects.export_run(self.run,'relative/path')
        with self.assertRaises(ValueError):projects.export_run(self.run,str(self.folder/'assets'))
        self.project['scenes'][0]['file']='../project.json'
        projects.atomic(self.run/'snapshot.json',self.project)
        with self.assertRaises(ValueError):projects.export_run(self.run,self.destination)
        self.assertEqual(list(Path(self.destination).iterdir()),[])

    def test_names_are_required_unique_and_rename_persists(self):
        with self.assertRaisesRegex(ValueError,'nhập tên'):projects.create('   ')
        with self.assertRaisesRegex(ValueError,'đã có'):projects.create('  Dự án có dấu / thử  ')
        renamed=projects.rename(self.project['id'],'Tập hai — Gia đình')
        self.assertEqual(projects.read(self.folder/'project.json')['name'],renamed['name'])
        second=projects.create('Tập ba')
        with self.assertRaisesRegex(ValueError,'đã có'):projects.rename(second['id'],'tập hai — gia đình')


if __name__=='__main__':unittest.main()
