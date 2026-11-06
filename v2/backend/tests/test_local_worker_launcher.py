import importlib.util
import json
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

spec = importlib.util.spec_from_file_location('lmt_local_worker', Path(__file__).parents[2] / 'start_local_worker.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def config():
    return dict(DATABASE_URL='postgresql://user:private-database-password@db.example.com/postgres?sslmode=require',
                SESSION_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                SUPABASE_URL='https://example.supabase.co',SUPABASE_SERVICE_ROLE_KEY='')


def test_saved_credentials_are_private_and_replaced_atomically(tmp_path):
    path=tmp_path/'settings'/'worker.json'
    first=config(); launcher.write_config(path,first)
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    assert stat.S_IMODE(path.parent.stat().st_mode)==0o700
    assert launcher.read_config(path)==first
    second=config(); launcher.write_config(path,second)
    assert launcher.read_config(path)==second
    assert list(path.parent.glob('.worker-*.tmp'))==[]


def test_failed_validation_never_overwrites_good_credentials(tmp_path):
    path=tmp_path/'settings'/'worker.json'
    first=config(); launcher.write_config(path,first)
    invalid=dict(first,SESSION_ENCRYPTION_KEY='not-a-fernet-key')
    with pytest.raises(ValueError): launcher.write_config(path,invalid)
    assert launcher.read_config(path)==first


def test_remote_database_requires_ssl_without_exposing_password():
    invalid=config(); invalid['DATABASE_URL']=invalid['DATABASE_URL'].split('?')[0]
    with pytest.raises(ValueError) as e: launcher.validate_config(invalid)
    assert 'private-database-password' not in str(e.value)
    with pytest.raises(ValueError): launcher.validate_config(dict(config(),SESSION_ENCRYPTION_KEY='wrong'))


def test_config_reader_refuses_symlink(tmp_path):
    original=tmp_path/'actual.json'; original.write_text(json.dumps(config()))
    link=tmp_path/'link.json'; link.symlink_to(original)
    with pytest.raises(ValueError): launcher.read_config(link)
