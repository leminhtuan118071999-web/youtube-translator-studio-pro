"""Smoke tests exercising the actual Streamlit entrypoint with AppTest.

No external keys, YouTube requests, live Supabase project or costs required.
"""
import unittest

from streamlit.testing.v1 import AppTest


class StreamlitSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file("streamlit_app.py", default_timeout=20)
        # AppTest has no browser localStorage or JavaScript component runtime.
        # Exercise the codec independently; UI tests begin after hydration.
        self.app.session_state["_browser_sessions_restored"] = True
        self.app.session_state["_session_name_test_fallback"] = True

    def test_thumbnail_ai_reuses_main_gemini_api_key(self):
        app = self.app.run()
        provider = next(
            item for item in app.selectbox if item.label == "CHỌN NỀN TẢNG AI"
        )
        provider.set_value("Google Gemini")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        shared = next(
            c for c in app.checkbox
            if c.key and c.key.endswith("_ai_use_shared")
        )
        self.assertTrue(shared.value)
        self.assertIn("Google Gemini", shared.label)
        self.assertTrue(any(
            item.label == "Model tạo/sửa ảnh" for item in app.selectbox
        ))
        # The UI must not force a duplicate key when sharing is enabled.
        self.assertFalse(any(
            item.key and "_image_key_" in item.key
            for item in app.get("text_input")
        ))

    def test_thumbnail_ai_shows_separate_image_provider_for_groq(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertFalse(any(
            c.key and c.key.endswith("_ai_use_shared") for c in app.checkbox
        ))
        self.assertTrue(any(
            item.label == "Dịch vụ chỉnh sửa ảnh"
            for item in app.selectbox
        ))

    def test_thumbnail_ai_panel_keeps_original_and_two_actions(self):
        from pathlib import Path
        code = Path("streamlit_app.py").read_text(encoding="utf-8")
        panel = Path("thumbnail_ui.py").read_text(encoding="utf-8")
        self.assertIn("render_thumbnail_ai(sid, vid, thumbnail if vid else None, language)", code)
        self.assertIn("Tạo lại thumbnail gốc", panel)
        self.assertIn("Dịch chữ trên thumbnail sang ngôn ngữ đích", panel)
        self.assertIn("normalize_thumbnail(source)", panel)
        self.assertIn("recognize_and_translate(", panel)
        self.assertIn("edit_thumbnail(", panel)
        self.assertIn('mime="image/png"', panel)
        self.assertIn('image_provider = st.selectbox(', panel)
        self.assertIn("Kết quả chỉ lưu trong phiên trình duyệt đang mở", panel)
        app = self.app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertTrue(any(
            button.key and button.key.endswith("_ai_recreate")
            for button in app.button
        ))
        self.assertTrue(any(
            button.key and button.key.endswith("_ai_translate")
            for button in app.button
        ))

    def test_unnecessary_completed_banner_and_session_count_caption_removed(self):
        from pathlib import Path
        source = Path("streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "✅ Phiên đã hoàn thành. Có thể Copy các mục trong những tab kết quả.",
            source,
        )
        self.assertNotIn("phiên đã chạy hoặc đang xử lý.", source)
        self.assertNotIn(
            "Có thể tạo phiên mới trong khi phiên cũ tiếp tục chạy.", source,
        )
        # Actual error and background-running status remain intact.
        self.assertIn("⚠️ Phiên này chưa hoàn tất:", source)
        self.assertIn("⏳ Phiên này đang xử lý:", source)
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])

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

    def test_session_colors_and_opening_session_priority(self):
        from pathlib import Path
        source = Path("streamlit_app.py").read_text(encoding="utf-8")
        # The new-session and saved-session styles are scoped to the sidebar.
        for snippet in (
            ".st-key-create_new_session button",
            "st-key-session_status_completed_",
            "st-key-session_status_pending_",
            'selected=is_selected',
            'label += " ✅"',
            "background: #16803e",
            "background: #c62828",
            'with st.container(key=f"session_status_{session_tone}_{saved_id}")',
        ):
            self.assertIn(snippet, source)

        app = self.app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertTrue(any(b.key == "create_new_session" for b in app.button))
        self.assertNotIn("st-key-session_status_selected_", source)
        self.assertNotIn("background: #facc15", source)
        first = app.session_state["selected_session"]
        app.session_state["workspaces"][first].update({
            "processed": True, "job_state": "completed",
        })
        next(b for b in app.button if b.key == "create_new_session").click()
        app.run()
        second = app.session_state["selected_session"]
        app.session_state["workspaces"][second].update({
            "processed": True, "job_state": "running",
        })
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(app.session_state["selected_session"], second)
        viewed = next(
            b for b in app.button if b.key == f"open_saved_session_{second}"
        )
        self.assertTrue(viewed.label.endswith(" ✅"))
        self.assertFalse(any(
            b.label.endswith(" ✅")
            for b in app.button
            if b.key == f"open_saved_session_{first}"
        ))
        self.assertTrue(any(
            b.key == f"open_saved_session_{first}" for b in app.button
        ))
        next(b for b in app.button
             if b.key == f"open_saved_session_{first}").click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(app.session_state["selected_session"], first)
        now_viewed = next(
            b for b in app.button if b.key == f"open_saved_session_{first}"
        )
        self.assertTrue(now_viewed.label.endswith(" ✅"))
        self.assertFalse(next(
            b for b in app.button if b.key == f"open_saved_session_{second}"
        ).label.endswith(" ✅"))
        self.assertEqual(
            app.session_state["workspaces"][second]["job_state"], "running"
        )

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

    def test_delete_one_purges_all_content_and_stages_browser_sync(self):
        from persistent_store import backup_state
        app = self.app.run()
        first = app.session_state["selected_session"]
        app.session_state["workspaces"][first].update({
            "processed": True,
            "saved": True,
            "translated": "SENSITIVE_DELETED_TRANSLATION",
            "prompts": "SENSITIVE_DELETED_PROMPTS",
            "new_description": "SENSITIVE_DELETED_SEO",
        })
        app.session_state["api_key_Groq"] = "preserve-provider-secret"
        next(btn for btn in app.button if btn.label == "➕ Tạo phiên mới").click()
        app.run()
        second = app.session_state["selected_session"]
        app.session_state["workspaces"][second]["processed"] = True
        app.run()
        next(btn for btn in app.button if btn.key == f"delete_session_{first}").click()
        app.run()
        next(btn for btn in app.button if btn.key == f"confirm_delete_{first}").click()
        app.run()
        state = app.session_state
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertNotIn(first, state["workspaces"])
        self.assertIn(second, state["workspaces"])
        self.assertTrue(state["_browser_delete_revision"])
        self.assertEqual(state["api_key_Groq"], "preserve-provider-secret")
        snapshot = backup_state(
            state["workspaces"], state["selected_session"],
            state["saved_session_order"],
        )
        payload = str(snapshot)
        self.assertNotIn("SENSITIVE_DELETED_TRANSLATION", payload)
        self.assertNotIn("SENSITIVE_DELETED_PROMPTS", payload)
        self.assertNotIn("SENSITIVE_DELETED_SEO", payload)

    def test_delete_all_purges_every_session_and_stages_browser_sync(self):
        from persistent_store import backup_state
        app = self.app.run()
        first = app.session_state["selected_session"]
        app.session_state["workspaces"][first].update({
            "processed": True, "saved": True, "translated": "FIRST_OLD_TRANSLATION",
        })
        next(btn for btn in app.button if btn.label == "➕ Tạo phiên mới").click()
        app.run()
        second = app.session_state["selected_session"]
        app.session_state["workspaces"][second].update({
            "processed": True, "saved": True, "translated": "SECOND_OLD_TRANSLATION",
        })
        app.session_state["api_key_Groq"] = "preserve-provider-secret"
        app.run()
        next(check for check in app.checkbox
             if check.key == "confirm_delete_all_sessions").set_value(True)
        app.run()
        next(btn for btn in app.button if btn.key == "delete_all_sessions").click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        state = app.session_state
        self.assertEqual(len(state["workspaces"]), 1)
        self.assertNotIn(first, state["workspaces"])
        self.assertNotIn(second, state["workspaces"])
        self.assertIn(state["selected_session"], state["workspaces"])
        self.assertEqual(state["background_jobs"], {})
        self.assertTrue(state["_browser_delete_revision"])
        self.assertEqual(state["api_key_Groq"], "preserve-provider-secret")
        payload = str(backup_state(
            state["workspaces"], state["selected_session"],
            state["saved_session_order"],
        ))
        self.assertNotIn("FIRST_OLD_TRANSLATION", payload)
        self.assertNotIn("SECOND_OLD_TRANSLATION", payload)

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

    def test_gemini_native_default_and_free_profile_without_losing_key(self):
        app = self.app.run()
        provider = next(
            item for item in app.selectbox if item.label == "CHỌN NỀN TẢNG AI"
        )
        provider.set_value("Google Gemini")
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(
            app.session_state["api_base_Google Gemini"],
            "https://generativelanguage.googleapis.com/v1beta",
        )
        self.assertEqual(
            app.session_state["api_model_id_Google Gemini"],
            "gemini-3.5-flash-lite",
        )
        key = next(
            item for item in app.get("text_input")
            if item.key == "api_key_Google Gemini"
        )
        key.set_value("FAKE_TEST_KEY_NOT_REAL")
        app.run()
        model = next(
            item for item in app.get("text_input")
            if item.key == "api_model_id_Google Gemini"
        )
        model.set_value("gemini-3.8-flash")
        app.run()
        next(
            button for button in app.button
            if button.key == "free_profile_Google Gemini"
        ).click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(
            app.session_state["api_model_id_Google Gemini"],
            "gemini-3.5-flash-lite",
        )
        self.assertEqual(
            app.session_state["api_key_Google Gemini"],
            "FAKE_TEST_KEY_NOT_REAL",
        )

    def test_groq_free_profile_is_selectable(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertTrue(any(
            button.key == "free_profile_Groq" for button in app.button
        ))
        next(
            item for item in app.get("text_input")
            if item.key == "api_model_id_Groq"
        ).set_value("openai/gpt-oss-120b")
        app.run()
        next(
            button for button in app.button
            if button.key == "free_profile_Groq"
        ).click()
        app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertEqual(
            app.session_state["api_model_id_Groq"], "openai/gpt-oss-20b"
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

    def test_hover_tooltips_removed_without_disabling_controls(self):
        import ast
        from pathlib import Path

        source = Path("streamlit_app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        hover_help = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.keyword) and node.arg == "help"
        ]
        self.assertEqual(hover_help, [])
        self.assertIn('[role="tooltip"]', source)
        self.assertIn('[data-baseweb="tooltip"]', source)
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        self.assertTrue(any(button.label == "➕ Tạo phiên mới" for button in app.button))
        self.assertTrue(any(
            panel.label == "🔑 Cấu hình API đa nền tảng"
            for panel in app.get("expander")
        ))

    def test_backup_section_removed_but_api_and_session_controls_remain(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        expanders = [exp.label for exp in app.get("expander")]
        self.assertNotIn("💾 Lưu dữ liệu và sao lưu", expanders)
        self.assertIn("🔑 Cấu hình API đa nền tảng", expanders)
        self.assertTrue(any(
            btn.label == "➕ Tạo phiên mới" for btn in app.button
        ))
        self.assertFalse(any(
            "bản sao các phiên" in btn.label.lower() for btn in app.button
        ))

    def test_txt_download_is_exclusive_to_translation(self):
        """Keep Copy for every section while downloading TXT only for translation."""
        import ast
        from pathlib import Path

        app = self.app.run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])

        source = Path("streamlit_app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        output_function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "output"
        )
        self.assertEqual(len(output_function.args.kwonlyargs), 1)
        self.assertEqual(output_function.args.kwonlyargs[0].arg, "allow_download")
        self.assertIsInstance(output_function.args.kw_defaults[0], ast.Constant)
        self.assertFalse(output_function.args.kw_defaults[0].value)

        download_calls = [
            node for node in ast.walk(output_function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "download_button"
        ]
        self.assertEqual(len(download_calls), 1)
        self.assertTrue(any(
            isinstance(branch, ast.If)
            and isinstance(branch.test, ast.Name)
            and branch.test.id == "allow_download"
            and download_calls[0] in list(ast.walk(branch))
            for branch in ast.walk(output_function)
        ))

        opted_in = [
            call for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name) and call.func.id == "output"
            and any(
                kw.arg == "allow_download"
                and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in call.keywords
            )
        ]
        self.assertEqual(len(opted_in), 1)
        self.assertEqual(opted_in[0].args[0].value, "📋 Copy toàn bộ bản dịch")
        # Existing copy actions for prompt/title/description/SEO remain available.
        for label in (
            "📋 Copy toàn bộ 20 prompt", "📋 Copy toàn bộ tiêu đề",
            "📋 Copy toàn bộ mô tả", "📋 Copy toàn bộ từ khóa SEO",
        ):
            self.assertIn(label, source)

    def test_translation_and_description_are_collapsed_but_keep_full_text(self):
        app = self.app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        sid = app.session_state["selected_session"]
        app.session_state["workspaces"][sid]["translated"] = (
            "Dòng dịch rất dài, đầy đủ không bị cắt. " * 12
        )
        app.session_state["workspaces"][sid]["new_description"] = (
            "Mô tả video dài, đầy đủ không bị cắt. " * 12
        )
        app.run()
        self.assertFalse(app.exception, [str(exc.message) for exc in app.exception])
        panels = [
            panel for panel in app.get("expander")
            if panel.label.startswith(("🌍 Bản dịch hoàn chỉnh", "📝 Mô tả đã dịch"))
        ]
        self.assertEqual(len(panels), 2)
        self.assertTrue(all("Nhấn để xem toàn bộ" in p.label for p in panels))
        # Streamlit AppTest exposes panel labels but not expanded state.
        # Verify the default collapse mode directly in the rendered app source.
        from pathlib import Path
        code = Path("streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn(
            'with st.expander(f"🌍 Bản dịch hoàn chỉnh ({language}) — '
            'Nhấn để xem toàn bộ", expanded=False):', code
        )
        self.assertIn(
            'with st.expander(f"📝 Mô tả đã dịch ({language}) — '
            'Nhấn để xem toàn bộ", expanded=False):', code
        )
        self.assertEqual(
            len(app.session_state["workspaces"][sid]["translated"]),
            len("Dòng dịch rất dài, đầy đủ không bị cắt. " * 12),
        )
        self.assertEqual(
            len(app.session_state["workspaces"][sid]["new_description"]),
            len("Mô tả video dài, đầy đủ không bị cắt. " * 12),
        )


if __name__ == "__main__":
    unittest.main()
