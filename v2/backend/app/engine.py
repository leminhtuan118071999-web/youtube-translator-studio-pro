"""Adapters to the existing V1 engines; no second AI implementation."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import json
from api_clients import PROVIDERS, generate_text, list_models, validate_base_url, migrate_claude_settings, migrate_free_provider_settings
from .text_pipeline import run_text_job


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
                image_api_key='')


def request_text(snapshot, prompt):
    return generate_text(snapshot['provider'], snapshot['base_url'], snapshot['model'],
                         snapshot['api_key'], prompt,
                         api_format=snapshot.get('api_format'), auth_mode=snapshot.get('auth_mode'))


def execute(kind, snapshot, progress, image_sink=None):
    return run_text_job(kind, snapshot, progress)
