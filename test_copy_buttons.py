"""Regression tests for visible copy-all actions without browser dependencies."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from copy_buttons import copy_all_button


class CopyButtonsTests(TestCase):
    def test_full_text_is_passed_to_browser_without_truncating(self):
        long_content = ("Dịch toàn bộ câu chuyện, chứa Unicode tiếng Việt và Ba Lan.\n" * 9000)
        with patch("copy_buttons._copy_component") as component:
            copy_all_button(
                "📋 Copy toàn bộ bản dịch", long_content,
                key="copy_all_translation_abc123",
            )
        component.assert_called_once_with(
            text=long_content,
            label="📋 Copy toàn bộ bản dịch",
            key="copy_all_translation_abc123",
            default=None,
        )

    def test_empty_result_creates_disabled_browser_button(self):
        with patch("copy_buttons._copy_component") as component:
            copy_all_button(
                "📋 Copy toàn bộ mô tả", "",
                key="copy_all_description_abc123",
            )
        self.assertEqual(component.call_args.kwargs["text"], "")

    def test_requires_distinct_nonempty_key_and_label(self):
        with patch("copy_buttons._copy_component"):
            with self.assertRaises(ValueError):
                copy_all_button("", "content", key="copy_123")
            with self.assertRaises(ValueError):
                copy_all_button("Copy", "content", key="")

    def test_clipboard_uses_click_and_supports_fallback(self):
        frontend = (Path(__file__).resolve().parent /
                    "copy_button_frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn('button.addEventListener("click"', frontend)
        self.assertIn("navigator.clipboard.writeText(source)", frontend)
        self.assertIn('document.execCommand("copy")', frontend)
        self.assertIn("button.disabled = !source", frontend)
        self.assertIn("✅ Đã copy", frontend)
        self.assertNotIn("localStorage", frontend)

    def test_copy_all_buttons_have_blue_raised_bold_style(self):
        frontend = (Path(__file__).resolve().parent /
                    "copy_button_frontend" / "index.html").read_text(encoding="utf-8")
        # All six copy-all actions share one browser component and therefore
        # the same visual style, including the disabled empty-result state.
        self.assertIn("linear-gradient(180deg, #3186ff 0%, #1461dc 100%)", frontend)
        self.assertIn("color: #fff;", frontend)
        self.assertIn("font: 800 13px/1.3", frontend)
        self.assertIn("text-shadow: 0 1px 1px", frontend)
        self.assertIn("box-shadow: 0 3px 0", frontend)
        self.assertIn("button:hover:enabled", frontend)
        self.assertIn("button:active:enabled", frontend)
        self.assertIn("button:disabled", frontend)
        self.assertIn("#5c9ded", frontend)
        self.assertIn("height: 56", frontend)
        self.assertNotIn("opacity: .43", frontend)

    def test_each_result_has_outside_copy_button(self):
        code = (Path(__file__).resolve().parent /
                "streamlit_app.py").read_text(encoding="utf-8")
        for key in (
            "copy_all_translation_", "copy_all_prompts_", "copy_all_title_",
            "copy_all_description_", "copy_all_seo_", "copy_all_legacy_seo_",
        ):
            self.assertIn(f'key=f"{key}{{sid}}"', code)
        self.assertLess(
            code.index('key=f"copy_all_translation_{sid}"'),
            code.index('with st.expander(f"🌍 Bản dịch hoàn chỉnh'),
        )
        self.assertLess(
            code.index('key=f"copy_all_description_{sid}"'),
            code.index('with st.expander(f"📝 Mô tả đã dịch'),
        )


if __name__ == "__main__":
    import unittest
    unittest.main()
