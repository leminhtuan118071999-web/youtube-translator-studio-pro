"""Portable, explicit backups of completed Streamlit work sessions.

Only textual work is exported. Never serialize API keys, Supadata keys,
the Streamlit state object, thread objects, or other runtime credentials.
"""
import json

FORMAT = "youtube-translator-studio-pro"
VERSION = 1
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_RECORDS = 120
MAX_FIELD_CHARS = 350_000

TEXT_FIELDS = (
    "name", "url", "source", "title", "description",
    "translated", "prompts", "metadata", "language",
    "new_title", "new_description", "seo_tags", "job_error",
)
ALLOWED_JOB_STATES = ("completed", "failed", "interrupted", "running", "")


def sanitize_record(record):
    if not isinstance(record, dict):
        raise ValueError("Thông tin phiên không hợp lệ.")
    result = {}
    for key in TEXT_FIELDS:
        val = record.get(key, "")
        if not isinstance(val, str) or len(val) > MAX_FIELD_CHARS:
            raise ValueError(f"Trường {key} không hợp lệ hoặc quá dài.")
        result[key] = val
    if not result["name"].strip():
        result["name"] = "Phiên khôi phục"
    result["name"] = result["name"][:80]
    order = record.get("saved_order", 0)
    if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order < 1_000_000:
        raise ValueError("Thứ tự phiên không hợp lệ.")
    result["saved_order"] = order
    raw_state = record.get("job_state", "")
    if raw_state not in ALLOWED_JOB_STATES:
        raise ValueError("Trạng thái phiên không hợp lệ.")
    # A restored file is never a currently-running background job.
    result["job_state"] = "interrupted" if raw_state == "running" else raw_state
    if raw_state == "running":
        result["job_error"] = "Phiên bị gián đoạn sau khi đóng ứng dụng. Kết quả đã sao lưu vẫn có thể xem."
    result["processed"] = True
    result["saved"] = True
    return result


def eligible_record(record):
    return bool(
        record.get("processed")
        or record.get("job_state") in ("running", "completed", "failed", "interrupted")
    )


def export_sessions(workspaces):
    chosen = [sanitize_record(rec) for rec in workspaces.values() if eligible_record(rec)]
    if len(chosen) > MAX_RECORDS:
        raise ValueError("Có quá nhiều phiên. Tối đa 120 phiên trong một tệp.")
    document = {"format": FORMAT, "version": VERSION, "sessions": chosen}
    data = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Sao lưu lớn hơn 12 MB. Hãy chia nhỏ dữ liệu trước khi tải.")
    return data


def import_sessions(payload):
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_FILE_BYTES:
        raise ValueError("File sao lưu rỗng hoặc vượt quá 12 MB.")
    try:
        obj = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("File không phải JSON UTF-8 hợp lệ.") from exc
    if not isinstance(obj, dict) or obj.get("format") != FORMAT or obj.get("version") != VERSION:
        raise ValueError("Sai định dạng sao lưu của YouTube Translator Studio Pro.")
    records = obj.get("sessions")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ValueError("Danh sách phiên không hợp lệ hoặc quá nhiều phiên.")
    return [sanitize_record(record) for record in records]
