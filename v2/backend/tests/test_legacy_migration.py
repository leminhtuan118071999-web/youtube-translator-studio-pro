import json

from cryptography.fernet import Fernet

from app.legacy_migration import inspect_legacy_state


def test_legacy_payload_and_encrypted_provider_settings_validate():
    key = Fernet.generate_key()
    settings = {
        "api_provider": "openai",
        "api_key_openai": "test-secret-value",
        "api_base_openai": "https://api.openai.com/v1",
    }
    encrypted = Fernet(key).encrypt(json.dumps(settings).encode()).decode()
    payload = {
        "version": 1,
        "workspaces": {
            "a" * 32: {"name": "Private session", "saved": True, "video_forms": "form"},
            "b" * 32: {"name": "Another session", "character_images_manifest": "[]"},
        },
        "selected_session": "a" * 32,
        "saved_session_order": 1,
    }

    report = inspect_legacy_state(payload, encrypted, key.decode())

    assert report["ready_for_import"] is True
    assert report["session_count"] == 2
    assert report["saved_session_count"] == 1
    assert report["provider_setting_count"] == 3
    assert report["encryption_verified"] is True
    assert "test-secret-value" not in json.dumps(report)
    assert "Private session" not in json.dumps(report)


def test_wrong_fernet_key_blocks_import_without_exposing_secret():
    correct_key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    encrypted = Fernet(correct_key).encrypt(b'{"api_key_openai":"secret"}').decode()
    payload = {"version": 1, "workspaces": {}, "selected_session": None}

    report = inspect_legacy_state(payload, encrypted, wrong_key.decode())

    assert report["ready_for_import"] is False
    assert "legacy_encryption_verification_failed" in report["errors"]
    assert "secret" not in json.dumps(report)


def test_invalid_session_identifier_is_reported():
    payload = {
        "version": 1,
        "workspaces": {"not-a-session-id": {"saved": True}},
        "selected_session": {"unexpected": "object"},
    }

    report = inspect_legacy_state(payload, "", "")

    assert report["ready_for_import"] is False
    assert report["invalid_session_id_count"] == 1
    assert report["selected_session_valid"] is False
