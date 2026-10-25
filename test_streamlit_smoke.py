"""Smoke tests exercising the actual Streamlit entrypoint with AppTest.

No external keys, YouTube requests, live Supabase project or costs required.
"""
import unittest

from streamlit.testing.v1 import AppTest


class StreamlitSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file("streamlit_app.py", default_timeout=20)

    def test_app_loads_and_can_create_new_session(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        names = [button.label for button in app.button]
        self.assertIn("➕ Tạo phiên mới", names)
        self.assertIn("🚀 BẮT ĐẦU TẠO TOÀN BỘ", names)
        original = app.session_state["selected_session"]
        for button in app.button:
            if button.label == "➕ Tạo phiên mới":
                button.click()
                break
        app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        self.assertNotEqual(app.session_state["selected_session"], original)
        self.assertEqual(len(app.session_state["workspaces"]), 2)

    def test_deleting_one_saved_session_preserves_other_sessions(self):
        app = self.app.run()
        first_id = app.session_state["selected_session"]
        app.session_state["workspaces"][first_id]["processed"] = True
        next(button for button in app.button
             if button.label == "➕ Tạo phiên mới").click()
        app.run()
        second_id = app.session_state["selected_session"]
        app.session_state["workspaces"][second_id]["processed"] = True
        app.run()
        next(button for button in app.button
             if button.key == f"delete_session_{first_id}").click()
        app.run()
        self.assertIn(first_id, app.session_state["workspaces"])
        self.assertTrue(any(
            button.key == f"confirm_delete_{first_id}" for button in app.button
        ))
        next(button for button in app.button
             if button.key == f"confirm_delete_{first_id}").click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertNotIn(first_id, app.session_state["workspaces"])
        self.assertIn(second_id, app.session_state["workspaces"])

    def test_deleting_last_session_keeps_app_operational(self):
        app = self.app.run()
        selected = app.session_state["selected_session"]
        app.session_state["workspaces"][selected]["processed"] = True
        app.run()
        next(button for button in app.button
             if button.key == f"delete_session_{selected}").click()
        app.run()
        next(button for button in app.button
             if button.key == f"confirm_delete_{selected}").click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertNotIn(selected, app.session_state["workspaces"])
        self.assertEqual(len(app.session_state["workspaces"]), 1)
        self.assertIn(app.session_state["selected_session"],
                      app.session_state["workspaces"])

    def test_claude_provider_is_selectable_and_exposes_api_key(self):
        app = self.app.run()
        selector = next(
            item for item in app.selectbox if item.label == "CHỌN NỀN TẢNG AI"
        )
        self.assertIn("Claude (Anthropic)", selector.options)
        selector.set_value("Claude (Anthropic)")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(app.session_state["api_provider"], "Claude (Anthropic)")
        self.assertTrue(any(
            item.label == "🔐 Claude API Key" for item in app.get("text_input")
        ))
        self.assertEqual(
            app.session_state["api_model_id_Claude (Anthropic)"],
            "claude-sonnet-4-6",
        )

    def test_language_selector_is_next_to_start_action(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        self.assertTrue(any(
            item.label == "🌍 Ngôn ngữ đích"
            for item in app.selectbox
        ))
        self.assertEqual(
            sum(item.label == "🌍 Ngôn ngữ đích" for item in app.selectbox), 1
        )

    def test_backup_section_is_visible_without_supabase(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        expanders = [exp.label for exp in app.get("expander")]
        self.assertIn("💾 Lưu dữ liệu và sao lưu", expanders)
        self.assertIn("🔑 Cấu hình API đa nền tảng", expanders)


if __name__ == "__main__":
    unittest.main()
