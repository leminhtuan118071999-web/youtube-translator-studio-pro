"""Tests for the double-click session-name UI and server-side rename rules."""
from pathlib import Path
import unittest
from unittest.mock import patch

from session_name_controls import rename_record, session_name_control


class SessionNameControlsTests(unittest.TestCase):
    def setUp(self):
        self.rows = {
            "first": {
                "name": "Câu chuyện 1", "translated": "Bản dịch phải được giữ",
                "job_state": "completed",
            },
            "second": {
                "name": "Câu chuyện 2", "translated": "Bản dịch riêng",
                "job_state": "running",
            },
        }

    def test_rename_updates_only_name_and_preserves_other_sessions(self):
        self.assertEqual(
            rename_record(self.rows, "first", "  Tên phiên mới  "), "Tên phiên mới"
        )
        self.assertEqual(self.rows["first"]["name"], "Tên phiên mới")
        self.assertEqual(self.rows["first"]["translated"], "Bản dịch phải được giữ")
        self.assertEqual(self.rows["first"]["job_state"], "completed")
        self.assertEqual(self.rows["second"]["name"], "Câu chuyện 2")

    def test_rejects_empty_duplicate_and_overlong_names(self):
        for bad in ("", " ", "CÂU CHUYỆN 2", "x" * 81, None):
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    rename_record(self.rows, "first", bad)
        with self.assertRaises(ValueError):
            rename_record(self.rows, "missing", "name")
        self.assertEqual(self.rows["first"]["name"], "Câu chuyện 1")

    @patch("session_name_controls._session_component")
    def test_component_receives_name_and_status_without_secret_fields(self, component):
        component.return_value = {"action": "open", "seq": "123"}
        self.assertEqual(
            session_name_control("Phiên A", " ⏳ 50%", "pending", key="session_a"),
            {"action": "open", "seq": "123"},
        )
        component.assert_called_once_with(
            name="Phiên A", suffix=" ⏳ 50%", tone="pending",
            key="session_a", default=None,
        )
        with self.assertRaises(ValueError):
            session_name_control("abc", "", "unknown", key="invalid")

    def test_frontend_doubleclick_inline_enter_and_singleclick(self):
        html = (Path(__file__).resolve().parent /
                "session_name_frontend" / "index.html").read_text(encoding="utf-8")
        for expected in (
            'button.addEventListener("click"',
            'button.addEventListener("dblclick"',
            'input.addEventListener("keydown"',
            'event.key === "Enter"',
            'event.key === "Escape"',
            'emit("open")',
            'emit("rename", proposed)',
            "clearTimeout(clickTimer)",
            'input.select()',
            "button.className = tone;",
            "button.textContent =",
            'button.setAttribute("aria-label"',
        ):
            self.assertIn(expected, html)
        for color in ("#facc15", "#16803e", "#c62828"):
            self.assertIn(color, html)
        self.assertNotIn("localStorage", html)

    def test_streamlit_ui_has_only_red_delete_next_to_name_without_ticks(self):
        source = (Path(__file__).resolve().parent /
                  "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('name_col, delete_col = st.columns([5.5, 1.5]', source)
        self.assertIn('key=f"delete_session_{saved_id}"', source)
        self.assertIn('background: #c62828 !important;', source)
        self.assertIn('key=f"session_name_control_{saved_id}"', source)
        self.assertNotIn('key=f"edit_session_{saved_id}"', source)
        self.assertNotIn('status_icon = " ✅"', source)
        self.assertNotIn('(" ✓" if saved_id == sid else "")', source)
        self.assertNotIn('on_change=rename_saved_session', source)


if __name__ == "__main__":
    unittest.main()
