"""Browser-only persistence for non-secret LMT Studio Pro session backups.

Compressed snapshots are kept in a localStorage key on the current browser
origin. Never include API credentials or provider settings in this payload.
Supabase remains the cross-device, per-account persistence mechanism.
"""
import base64
import hashlib
import json
import zlib

from persistent_store import MAX_BYTES, normalize_sessions

STORAGE_KEY = "lmt-studio-pro:session-backup:v1"
API_SETTINGS_STORAGE_KEY = "lmt-studio-pro:encrypted-api-settings:v1"
MAX_LOCAL_CHARACTERS = 2_000_000


def encode_browser_backup(payload):
    """Return a compact, integrity-checked JSON value for browser localStorage."""
    clean = normalize_sessions(payload)
    raw = json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("Danh sách phiên vượt 7 MB; hãy tải bản sao lưu JSON.")
    compressed = base64.b64encode(zlib.compress(raw, level=6)).decode("ascii")
    encoded = json.dumps(
        {"version": 1, "sha256": hashlib.sha256(raw).hexdigest(), "data": compressed},
        separators=(",", ":"),
    )
    if len(encoded) > MAX_LOCAL_CHARACTERS:
        raise ValueError(
            "Bộ nhớ trình duyệt có thể không đủ cho toàn bộ phiên. "
            "Hãy tải bản sao lưu JSON hoặc bật Supabase."
        )
    return encoded


def decode_browser_backup(encoded):
    """Validate and strictly bound decompression of a browser-provided snapshot."""
    if not isinstance(encoded, str) or len(encoded) > MAX_LOCAL_CHARACTERS:
        raise ValueError("Dữ liệu tự lưu của trình duyệt không hợp lệ hoặc quá lớn.")
    try:
        envelope = json.loads(encoded)
        if not isinstance(envelope, dict) or envelope.get("version") != 1:
            raise ValueError("Phiên bản sao lưu trình duyệt không được hỗ trợ.")
        encoded_bytes = envelope.get("data", "")
        if not isinstance(encoded_bytes, str):
            raise ValueError("Dữ liệu phiên không hợp lệ.")
        packed = base64.b64decode(encoded_bytes, validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(packed, MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or not inflater.eof or inflater.unused_data:
            raise ValueError("Dữ liệu phiên vượt giới hạn hoặc không hoàn chỉnh.")
        if hashlib.sha256(raw).hexdigest() != envelope.get("sha256"):
            raise ValueError("Dữ liệu phiên lưu trong trình duyệt bị thay đổi.")
        restored = normalize_sessions(json.loads(raw.decode("utf-8")))
        if not restored["workspaces"]:
            raise ValueError("Bản sao lưu không có phiên hợp lệ.")
        return restored
    except (TypeError, UnicodeError, json.JSONDecodeError, zlib.error, ValueError) as exc:
        raise ValueError("Không khôi phục được bản tự lưu của trình duyệt: " + str(exc)) from exc
