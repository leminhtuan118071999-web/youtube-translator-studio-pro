"""One-click copy actions that stay visible outside collapsed result panels.

Clipboard access happens only on a user's click in the browser. Text is never
written to Streamlit session state, logs, URLs, or any persistence system here.
"""
from pathlib import Path

import streamlit.components.v1 as components


_copy_component = components.declare_component(
    "lmt_studio_copy_output",
    path=str(Path(__file__).resolve().parent / "copy_button_frontend"),
)


def copy_all_button(label: str, text: str, *, key: str) -> None:
    """Display a single always-visible copy button with the full uncut text.

    The browser component performs the clipboard write after a real user click;
    its return value is ignored to avoid repeated Streamlit script reruns.
    """
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Nhãn nút sao chép không hợp lệ.")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Thiếu khóa riêng cho nút sao chép.")
    _copy_component(
        text=text if isinstance(text, str) else "",
        label=label,
        key=key,
        default=None,
    )
