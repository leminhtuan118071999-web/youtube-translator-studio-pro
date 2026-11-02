"""Render dynamic session notices without exposing text to page translators."""
from html import escape

_COLORS = {
    "info": ("rgba(28,131,225,.12)", "#60a5fa"),
    "error": ("rgba(255,75,75,.15)", "#f87171"),
}


def session_notice_html(text, *, error=False):
    background, border = _COLORS["error" if error else "info"]
    # Escape session names and provider messages: they are plain text, never HTML.
    return (
        '<div class="notranslate" translate="no" role="status" '
        'aria-live="polite" style="padding:16px;border-radius:8px;'
        f'border-left:3px solid {border};background:{background};'
        'color:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:16px">'
        f'<span class="notranslate" translate="no">{escape(str(text))}</span></div>'
    )
