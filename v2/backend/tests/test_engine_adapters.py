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


@pytest.mark.parametrize('bible', ['', 'Lan waters plants.'])
def test_forms_do_not_run_detailed_character_or_translation_jobs(bible):
    snapshot = dict(translated='Lan tưới cây.', language='Tiếng Việt', style='2D',
                    duration_seconds=8, api_key='test-key', character_bible=bible)
    def provider(_snapshot, prompt):
        if prompt.startswith('FORM_CONTINUITY_REFERENCE'):
            return '{"character_bible":"Lan waters plants."}'
        if prompt.startswith('Translate this fixed'):
            return '{"character_bible":"Lan waters plants."}'
        if prompt.startswith('Write visual_prompt'):
            return json.dumps({'scenes':[{'number':1, 'visual_prompt':'Lan waters plants.',
                'image_prompt':'Opening frame: Lan beside a plant.', 'transition_to_next':'',
                'speech_segments':[{'kind':'narrator','speaker':'narrator','text':'Lan tưới cây.'}]}]})
        if prompt.startswith('FORM_LANGUAGE_CHECK'):
            return '{"ok":true,"issues":[]}'
        raise AssertionError('Unexpected AI operation: '+prompt[:100])
    with patch('server_video_jobs._provider_call', side_effect=provider), \
         patch('server_video_jobs.prepare_video_profiles', side_effect=AssertionError('Detailed profile must be requested separately')), \
         patch('app.engine.run_full_job', side_effect=AssertionError('Must not translate again')), \
         patch('app.engine.run_character_job', side_effect=AssertionError('Must not start character job')):
        result = execute('forms', snapshot, JobProgress())
    assert result['ok'], result['error']
    assert 'character_profile_json' not in result['fields']
    assert 'character_bible' not in result['fields']
    assert 'translated' not in result['fields']
    assert 'new_description' not in result['fields']
    plan = json.loads(result['fields']['video_forms'])
    assert len(plan['scenes']) == 1
    assert plan['scenes'][0]['voiceover'] == snapshot['translated']
