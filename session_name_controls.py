"""Session-name control: single-click to open, double-click to rename.

The browser component handles click timing and inline editing. Back-end
validation rejects blank/duplicate names without changing other sessions.
"""
from pathlib import Path
import streamlit.components.v1 as components


_session_component = components.declare_component(
    "lmt_studio_session_name",
    path=str(Path(__file__).resolve().parent / "session_name_frontend"),
)


def session_name_control(name, suffix, tone, *, selected=False, key):
    if tone not in ("completed", "pending"):
        raise ValueError("Màu trạng thái phiên không hợp lệ.")
    if not isinstance(selected, bool):
        raise ValueError("Trạng thái phiên đang xem không hợp lệ.")
    return _session_component(
        name=str(name), suffix=str(suffix), tone=tone,
        selected=selected, key=key, default=None,
    )


def rename_record(workspaces, session_id, new_name):
    if session_id not in workspaces:
        raise ValueError("Không tìm thấy phiên cần đổi tên.")
    if not isinstance(new_name, str):
        raise ValueError("Tên phiên không hợp lệ.")
    name = new_name.strip()
    if not name:
        raise ValueError("Tên phiên không được để trống.")
    if len(name) > 80:
        raise ValueError("Tên phiên không được dài quá 80 ký tự.")
    if any(
        other_id != session_id
        and str(record.get("name", "")).casefold() == name.casefold()
        for other_id, record in workspaces.items()
    ):
        raise ValueError("Tên phiên đã tồn tại. Hãy chọn tên khác.")
    workspaces[session_id]["name"] = name
    return name
