import json
from unittest.mock import patch
import pytest
from app.engine import execute
from app.worker import Progress
from background_jobs import JobProgress


@pytest.mark.parametrize('existing', [{}, {'_profile_build': {'scanned': 1}, '_profile_job': {'state': 'failed'}}])
def test_character_adapter_initializes_job_and_preserves_resume(existing):
    snapshot = dict(translated='Lan tưới cây.', language='Tiếng Việt', style='2D',
                    api_key='test-key', character_profile_json=json.dumps(existing))
    progress = JobProgress()
    profile = {'characters': [{'name': 'Lan'}], 'character_bible': 'Lan: áo xanh.'}
    with patch('server_character_jobs.build_character_profiles', return_value=profile) as build:
        result = execute('characters', snapshot, progress)
    assert result['ok'], result['error']
    saved = json.loads(result['fields']['character_profile_json'])
    assert saved['characters'] == profile['characters']
    assert saved['_profile_job']['state'] == 'completed'
    assert build.call_args.kwargs['state'] == existing.get('_profile_build')
    assert snapshot['character_profile_json'] == json.dumps(existing)


def test_v2_form_limit_accounts_for_unicode_json_envelope():
    Progress.validate_form_checkpoint('x' * 500_000)
    # A Unicode string can fit a character count but exceed the JSON envelope.
    with pytest.raises(ValueError, match='Checkpoint quá lớn'):
        Progress.validate_form_checkpoint('漢' * 1_400_000)
