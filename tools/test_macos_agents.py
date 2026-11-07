import plistlib
from pathlib import Path
import unittest
from tools.macos_agents import spec


class AgentTests(unittest.TestCase):
    def test_separate_agents_and_paths_with_spaces_roundtrip(self):
        for kind, entry in [('v2', 'v2/start_local_worker.py'), ('v3', 'v3/start_editor.py')]:
            root = Path('/Users/example/LMT project ' + kind)
            value = plistlib.loads(plistlib.dumps(spec(kind, root, Path('/Python/bin/python3'), Path('/Logs/LMT'))))
            self.assertEqual(value['ProgramArguments'], ['/Python/bin/python3', str(root / entry)])
            self.assertEqual(value['WorkingDirectory'], str(root))
            self.assertTrue(value['KeepAlive'])
            self.assertGreaterEqual(value['ThrottleInterval'], 60)
            self.assertNotIn('DATABASE_URL', value['EnvironmentVariables'])
            self.assertIn('ffmpeg-full', value['EnvironmentVariables']['PATH'])
        self.assertNotEqual(spec('v2', root, root, root)['Label'], spec('v3', root, root, root)['Label'])


if __name__ == '__main__':
    unittest.main()
