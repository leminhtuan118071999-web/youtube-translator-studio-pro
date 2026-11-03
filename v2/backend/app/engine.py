"""Adapters to the existing V1 engines; no second AI implementation."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import json
from api_clients import PROVIDERS, generate_text, list_models, validate_base_url, migrate_claude_settings, migrate_free_provider_settings
from background_jobs import run_full_job, overview
from server_video_jobs import run_video_forms_job
from server_character_jobs import run_character_job, profile_data
from youtube_metadata import generate_youtube_metadata
from character_images import create_character_png, detailed_character_profiles, character_reference_description
from video_scene_planner import continuous_combined_forms_text


def provider_snapshot(config):
    config = dict(config)
    migrate_claude_settings(config)
    migrate_free_provider_settings(config)
    provider = config.get('api_provider', 'Groq')
    if provider not in PROVIDERS:
        raise ValueError('Nhà cung cấp AI không hợp lệ.')
    defaults = PROVIDERS[provider]
    base = config.get(f'api_base_{provider}') or defaults['base_url']
    model = config.get(f'api_model_id_{provider}') or defaults['model']
    key = config.get(f'api_key_{provider}', '')
    if not key or not model:
        raise ValueError('Hãy cấu hình API key và model trước khi chạy.')
    validate_base_url(base)
    return dict(provider=provider, base_url=base, model=model, api_key=key,
                api_format=config.get(f'api_format_{provider}', 'chat'),
                auth_mode=config.get(f'api_auth_mode_{provider}', defaults.get('auth', 'bearer')))


def snapshot_for(data, config):
    return dict(data, **provider_snapshot(config),
                supadata_key=config.get('supadata_api_key_input', ''),
                image_api_key=config.get('image_api_key_input', ''))


def request_text(snapshot, prompt):
    return generate_text(snapshot['provider'], snapshot['base_url'], snapshot['model'],
                         snapshot['api_key'], prompt,
                         api_format=snapshot.get('api_format'), auth_mode=snapshot.get('auth_mode'))


def execute(kind, snapshot, progress, image_sink=None):
    """Checkpoints belong to the V2 job; never write into V1."""
    snapshot = dict(snapshot, cloud=None)
    if kind in ('full', 'translation'):
        return run_full_job(snapshot, progress)
    if kind == 'forms':
        snapshot.update(existing_plan=progress.partial_result().get('video_forms', snapshot.get('video_forms', '')),
                        audio_hash=snapshot.get('audio_hash', ''), audio_name=snapshot.get('audio_name', ''),
                        auto_form_language=True, known_translation_language=snapshot['language'],
                        auto_character_profiles=True, verify_form_language=True)
        for field in ('character_profile_json', 'character_bible', 'repair_memory_json'):
            if field in progress.partial_result():
                snapshot[field] = progress.partial_result()[field]
        return run_video_forms_job(snapshot, progress)
    if kind == 'characters':
        snapshot['character_profile_json'] = progress.partial_result().get(
            'character_profile_json', snapshot.get('character_profile_json', ''))
        data = profile_data(snapshot)
        data['_profile_job'] = dict(data.get('_profile_job') or {}, state='running', error='')
        snapshot['character_profile_json'] = json.dumps(data, ensure_ascii=False)
        return run_character_job(snapshot, progress)
    if kind == 'seo':
        progress.check_cancelled()
        call = lambda prompt: request_text(snapshot, prompt)
        brief = overview(snapshot['translated'], call, progress)
        title, description, tags = generate_youtube_metadata(
            brief, snapshot.get('title', ''), snapshot.get('description', ''), snapshot['language'], call)
        fields = dict(new_title=title, new_description=description, seo_tags=tags,
                      metadata='\n\n'.join((title, description, tags)))
        for field, value in fields.items():
            progress.publish(field, value)
        return dict(ok=True, fields=fields, error='')
    if kind == 'images':
        if not image_sink or not snapshot.get('image_api_key'):
            raise ValueError('Cần API ảnh và cấu hình Storage trên worker để lưu ảnh bền vững.')
        sheets = detailed_character_profiles(json.loads(snapshot.get('character_profile_json') or '{}'))
        specs = [(sheet['name'], character_reference_description(sheet)) for sheet in sheets][:10]
        if not specs:
            raise ValueError('Hãy tạo hồ sơ nhân vật trước khi tạo ảnh.')
        manifest = json.loads(progress.partial_result().get('character_images_manifest', '[]'))
        for name, description in specs:
            progress.check_cancelled()
            if any(item['name'] == name for item in manifest):
                continue
            png = create_character_png(snapshot['image_api_key'], name, description,
                                       style=snapshot['style'], bible=snapshot.get('character_bible', ''))
            path = image_sink(name, png)
            manifest.append(dict(name=name, path=path))
            progress.publish('character_images_manifest', json.dumps(manifest, ensure_ascii=False))
            progress.update(100 * len(manifest) / len(specs), f'Đã lưu ảnh {name}')
        return dict(ok=True, fields=dict(character_images_manifest=json.dumps(manifest, ensure_ascii=False)), error='')
    raise ValueError('Loại tác vụ không hợp lệ.')
