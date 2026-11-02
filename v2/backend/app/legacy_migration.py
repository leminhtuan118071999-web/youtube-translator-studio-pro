"""Read-only V1 compatibility inspection.

This module deliberately reports metadata only. It never returns plaintext
provider credentials, session contents, user names, or legacy IDs.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

MAX_SESSIONS = 150
ALLOWED_EXACT = {"api_provider", "supadata_api_key_input", "image_api_key_input"}
ALLOWED_PREFIXES = (
    "api_key_",
    "api_base_",
    "api_model_id_",
    "api_format_",
    "api_auth_mode_",
)


def inspect_legacy_state(
    payload: Any,
    encrypted_config: str | None,
    encryption_key: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {
            "ready_for_import": False,
            "errors": ["legacy_payload_not_object"],
            "warnings": [],
            "session_count": 0,
            "provider_setting_count": 0,
            "encryption_verified": False,
        }

    try:
        payload_bytes = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    except (TypeError, ValueError):
        payload_hash = None
        errors.append("legacy_payload_not_json_serializable")

    version = payload.get("version")
    if version not in (1, "1"):
        warnings.append("legacy_payload_version_unrecognized")

    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, dict):
        errors.append("legacy_workspaces_not_object")
        workspaces = {}

    session_count = len(workspaces)
    if session_count > MAX_SESSIONS:
        errors.append("legacy_session_limit_exceeded")

    invalid_session_ids = 0
    invalid_session_records = 0
    saved_session_count = 0
    sessions_with_image_manifest = 0
    sessions_with_video_forms = 0

    for session_id, record in workspaces.items():
        if not isinstance(session_id, str) or re.fullmatch(r"[a-f0-9]{32}", session_id) is None:
            invalid_session_ids += 1
        if not isinstance(record, dict):
            invalid_session_records += 1
            continue
        if bool(record.get("saved")):
            saved_session_count += 1
        if record.get("character_images_manifest"):
            sessions_with_image_manifest += 1
        if record.get("video_forms"):
            sessions_with_video_forms += 1

    if invalid_session_ids:
        errors.append("legacy_session_ids_invalid")
    if invalid_session_records:
        errors.append("legacy_session_records_invalid")

    selected_session = payload.get("selected_session")
    selected_session_valid = (
        selected_session is None
        or (isinstance(selected_session, str) and selected_session in workspaces)
    )
    if not selected_session_valid:
        warnings.append("selected_session_missing_or_invalid")

    encrypted_config = encrypted_config or ""
    encryption_verified = not bool(encrypted_config)
    provider_setting_count = 0
    unknown_setting_count = 0
    invalid_setting_count = 0

    if encrypted_config:
        if not encryption_key:
            errors.append("legacy_encryption_key_missing")
        else:
            try:
                cipher = Fernet(encryption_key.encode("ascii"))
                plaintext = cipher.decrypt(encrypted_config.encode("ascii"))
                settings = json.loads(plaintext.decode("utf-8"))
                if not isinstance(settings, dict):
                    raise ValueError("settings_not_object")

                encryption_verified = True
                for name, value in settings.items():
                    allowed = (
                        isinstance(name, str)
                        and (
                            name in ALLOWED_EXACT
                            or any(name.startswith(prefix) for prefix in ALLOWED_PREFIXES)
                        )
                    )
                    if not allowed:
                        unknown_setting_count += 1
                    if not isinstance(value, str) or len(value) >= 10000:
                        invalid_setting_count += 1
                    else:
                        provider_setting_count += 1

                if unknown_setting_count:
                    warnings.append("unknown_provider_setting_keys_preserved")
                if invalid_setting_count:
                    errors.append("provider_settings_invalid")
            except (InvalidToken, UnicodeError, ValueError, TypeError):
                errors.append("legacy_encryption_verification_failed")

    return {
        "ready_for_import": not errors,
        "errors": errors,
        "warnings": warnings,
        "legacy_payload_version": version,
        "legacy_payload_sha256": payload_hash,
        "session_count": session_count,
        "saved_session_count": saved_session_count,
        "invalid_session_id_count": invalid_session_ids,
        "invalid_session_record_count": invalid_session_records,
        "selected_session_valid": selected_session_valid,
        "sessions_with_character_image_manifest": sessions_with_image_manifest,
        "sessions_with_video_forms": sessions_with_video_forms,
        "provider_setting_count": provider_setting_count,
        "unknown_provider_setting_count": unknown_setting_count,
        "encryption_verified": encryption_verified,
        "encrypted_config_bytes": len(encrypted_config.encode("utf-8")),
    }
