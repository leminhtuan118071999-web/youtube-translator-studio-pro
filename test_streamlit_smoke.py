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

    def test_claude_gateway_shows_separate_auth_token_field(self):
        app = self.app.run()
        selector = next(
            item for item in app.selectbox if item.label == "CHỌN NỀN TẢNG AI"
        )
        self.assertIn("Claude Gateway (AUTH_TOKEN)", selector.options)
        selector.set_value("Claude Gateway (AUTH_TOKEN)")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertTrue(any(
            item.label == "🔐 Gateway AUTH_TOKEN"
            for item in app.get("text_input")
        ))
        self.assertEqual(
            app.session_state["api_model_id_Claude Gateway (AUTH_TOKEN)"],
            "claude-sonnet-4-6",
        )

    def test_custom_url_under_official_claude_offers_gateway_switch(self):
        app = self.app.run()
        provider = next(item for item in app.selectbox if item.label == "CHỌN NỀN TẢNG AI")
        provider.set_value("Claude (Anthropic)")
        app.run()
        base = next(
            item for item in app.get("text_input")
            if item.key == "api_base_Claude (Anthropic)"
        )
        base.set_value("https://gateway.example.com")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        switch = next(
            button for button in app.button
            if button.key == "switch_to_claude_gateway"
        )
        switch.click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(app.session_state["api_provider"], "Claude Gateway (AUTH_TOKEN)")
        self.assertEqual(
            app.session_state["api_base_Claude Gateway (AUTH_TOKEN)"],
            "https://gateway.example.com",
        )

    def test_editable_third_party_api_fields_and_protocol(self):
        app = self.app.run()
        selector = next(
            item for item in app.selectbox if item.label == "CHỌN NỀN TẢNG AI"
        )
        self.assertIn("API bên thứ ba (tùy chỉnh)", selector.options)
        selector.set_value("API bên thứ ba (tùy chỉnh)")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        proto = next(item for item in app.selectbox if item.label == "📡 Chuẩn API")
        self.assertIn("Anthropic Messages", proto.options)
        proto.set_value("Anthropic Messages")
        app.run()
        auth = next(item for item in app.selectbox if item.label == "🔏 Kiểu xác thực")
        auth.set_value("x-api-key")
        app.run()
        base = next(
            item for item in app.get("text_input")
            if item.key == "api_base_API bên thứ ba (tùy chỉnh)"
        )
        base.set_value("https://example.net/v1")
        app.run()
        model = next(
            item for item in app.get("text_input")
            if item.key == "api_model_id_API bên thứ ba (tùy chỉnh)"
        )
        model.set_value("my-custom-model")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(
            app.session_state["api_format_API bên thứ ba (tùy chỉnh)"],
            "Anthropic Messages",
        )
        self.assertEqual(
            app.session_state["api_auth_mode_API bên thứ ba (tùy chỉnh)"],
            "x-api-key",
        )
        self.assertEqual(
            app.session_state["api_base_API bên thứ ba (tùy chỉnh)"],
            "https://example.net/v1",
        )
        self.assertEqual(
            app.session_state["api_model_id_API bên thứ ba (tùy chỉnh)"],
            "my-custom-model",
        )
        self.assertTrue(any(
            item.key == "api_key_API bên thứ ba (tùy chỉnh)"
            for item in app.get("text_input")
        ))

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
