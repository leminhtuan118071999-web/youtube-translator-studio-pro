import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from v2 import background_worker as worker


class BackgroundWorkerTests(unittest.TestCase):
    def test_plist_uses_absolute_arguments_and_no_credentials(self):
        spec=worker.launch_spec(Path('/python/bin/python3'),Path('/Users/test/LMT V2/v2'),Path('/Users/test/Library/Logs/LMTStudioPro'))
        decoded=plistlib.loads(plistlib.dumps(spec))
        self.assertEqual(decoded['ProgramArguments'],['/python/bin/python3','/Users/test/LMT V2/v2/start_local_worker.py'])
        self.assertTrue(decoded['RunAtLoad'])
        self.assertEqual(decoded['KeepAlive'],{'SuccessfulExit':False})
        self.assertEqual(decoded['ThrottleInterval'],30)
        for key in ('DATABASE_URL','SESSION_ENCRYPTION_KEY','SUPABASE_SERVICE_ROLE_KEY'):
            self.assertNotIn(key,str(decoded))

    def test_install_registers_only_our_worker_and_preserves_config(self):
        from v2 import start_local_worker as bootstrap
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);config=home/'worker.json';config.write_text('private')
            plist=home/'LaunchAgents'/f'{worker.LABEL}.plist';logs=home/'Logs'
            with patch.object(worker,'paths',return_value=(plist,logs)), \
                 patch.object(bootstrap,'CONFIG_PATH',config), \
                 patch.object(bootstrap,'read_config',return_value={}) as validate, \
                 patch.object(worker,'launchctl',return_value=SimpleNamespace(returncode=0)) as ctl:
                worker.install()
            validate.assert_called_once_with(config)
            self.assertEqual(config.read_text(),'private')
            self.assertEqual(plist.stat().st_mode&0o777,0o600)
            data=plistlib.loads(plist.read_bytes());self.assertEqual(data['Label'],worker.LABEL)
            self.assertEqual(ctl.call_args_list[-1].args,('bootstrap',f'gui/{os.getuid()}',str(plist)))
            self.assertTrue(all('v3' not in str(call) for call in ctl.call_args_list))

    def test_invalid_config_never_stops_existing_worker(self):
        from v2 import start_local_worker as bootstrap
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'worker.json';config.write_text('invalid')
            with patch.object(bootstrap,'CONFIG_PATH',config), \
                 patch.object(bootstrap,'read_config',side_effect=ValueError('invalid')), \
                 patch.object(worker,'launchctl') as ctl:
                with self.assertRaises(ValueError):worker.install()
                ctl.assert_not_called()


if __name__=='__main__':unittest.main()
