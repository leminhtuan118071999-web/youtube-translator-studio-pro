"""The optional Thumbnail AI panel, independent of translation provider."""
import hashlib

import streamlit as st

from thumbnail_ai import (
    GEMINI_IMAGE_MODELS, OPENAI_IMAGE_MODELS,
    normalize_thumbnail, recognize_and_translate, build_edit_prompt, edit_thumbnail,
)


def render_thumbnail_ai(sid, vid, original_thumbnail, language):
    with st.expander("🎨 Thumbnail AI – Tạo lại ảnh / Dịch chữ trên ảnh", expanded=False):
        st.caption(
            f"Giữ phong cách ảnh gốc; tạo lại ảnh hoặc xóa chữ cũ và "
            f"thay bằng **{language}**. Xuất PNG 1280 × 720."
        )
        uploaded = st.file_uploader(
            "🖼️ Tải ảnh thumbnail khác (không bắt buộc nếu đã có link YouTube)",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"thumb_{sid}_ai_upload",
        )
        source = uploaded.getvalue() if uploaded else original_thumbnail
        if uploaded:
            st.image(source, caption="Ảnh thumbnail tải lên", width=500)
        if not source:
            st.info("Dán link YouTube hợp lệ hoặc tải ảnh thumbnail lên để bắt đầu.")

        image_provider = st.selectbox(
            "Dịch vụ chỉnh sửa ảnh",
            ["Gemini", "OpenAI"],
            key=f"thumb_{sid}_image_provider",
            help="Chọn Gemini hoặc OpenAI: các model Groq/Claude xử lý văn bản không tự tạo ảnh.",
        )
        models = GEMINI_IMAGE_MODELS if image_provider == "Gemini" else OPENAI_IMAGE_MODELS
        image_model = st.selectbox(
            "Model tạo/sửa ảnh",
            list(models),
            key=f"thumb_{sid}_image_model_{image_provider}",
        )
        supplied_key = st.text_input(
            "🔐 API key tạo ảnh (có thể để trống nếu đã nhập API key Gemini/OpenAI)",
            type="password", key=f"thumb_{sid}_image_key_{image_provider}",
        )
        api_id = "Google Gemini" if image_provider == "Gemini" else "OpenAI"
        configured_key = str(st.session_state.get(f"api_key_{api_id}", "") or "").strip()
        try:
            secret_key = str(st.secrets.get(
                "GEMINI_API_KEY" if image_provider == "Gemini" else "OPENAI_API_KEY", ""
            ) or "").strip()
        except (FileNotFoundError, OSError, KeyError, AttributeError):
            secret_key = ""
        image_key = supplied_key.strip() or configured_key or secret_key
        preserve = st.checkbox(
            "Giữ bố cục, nhân vật và phong cách ảnh gốc tối đa",
            value=True, key=f"thumb_{sid}_ai_preserve",
        )
        remove_text = st.checkbox(
            "Xóa sạch chữ cũ và căn lại bố cục chữ",
            value=True, key=f"thumb_{sid}_ai_inpaint",
        )
        st.caption(
            "Dùng model tạo ảnh có hỗ trợ chỉnh sửa ảnh nguồn. "
            "Gói miễn phí thường không bao gồm model ảnh; mỗi lần tạo có thể tính phí."
        )
        recreate_col, translate_col = st.columns(2, gap="small")
        with recreate_col:
            recreate_clicked = st.button(
                "🖼️ Tạo lại thumbnail gốc", use_container_width=True,
                key=f"thumb_{sid}_ai_recreate", disabled=not bool(source),
            )
        with translate_col:
            translate_clicked = st.button(
                "🌍 Dịch chữ trên thumbnail sang ngôn ngữ đích",
                use_container_width=True, key=f"thumb_{sid}_ai_translate",
                disabled=not bool(source),
            )

        if recreate_clicked or translate_clicked:
            mode = "translate" if translate_clicked else "recreate"
            if not image_key:
                st.warning(
                    "Nhập API key Gemini hoặc OpenAI có quyền dùng model ảnh để tiếp tục."
                )
            else:
                try:
                    clean_source = normalize_thumbnail(source)
                    new_hash = hashlib.sha256(clean_source).hexdigest()
                    hash_key = f"thumb_{sid}_ai_source_hash"
                    if st.session_state.get(hash_key) != new_hash:
                        for prev_mode in ("recreate", "translate"):
                            st.session_state.pop(f"thumb_{sid}_ai_{prev_mode}_png", None)
                        st.session_state.pop(f"thumb_{sid}_ai_ocr", None)
                    st.session_state[hash_key] = new_hash
                    original_text, translated_text = "", ""
                    if mode == "translate":
                        with st.spinner("🔎 AI đang đọc và dịch chữ trên thumbnail..."):
                            original_text, translated_text = recognize_and_translate(
                                clean_source, language, image_provider, image_key,
                            )
                        if not original_text:
                            st.warning(
                                "Không nhận diện được chữ trên ảnh. "
                                "Hãy thử thumbnail có chữ rõ ràng hơn."
                            )
                        else:
                            st.session_state[f"thumb_{sid}_ai_ocr"] = {
                                "original": original_text,
                                "translated": translated_text,
                                "language": language,
                            }
                    if mode == "recreate" or original_text:
                        prompt = build_edit_prompt(
                            mode, language,
                            original_text=original_text,
                            translated_text=translated_text,
                            preserve_layout=preserve,
                            clean_text=remove_text,
                        )
                        with st.spinner(
                            "🎨 AI đang dựng lại thumbnail, xóa chữ cũ và căn bố cục..."
                        ):
                            output = edit_thumbnail(
                                clean_source, prompt, image_provider, image_key, image_model,
                            )
                        st.session_state[f"thumb_{sid}_ai_{mode}_png"] = output
                        st.success("✅ Đã tạo thumbnail mới. Hãy tải ảnh về để lưu kết quả.")
                except Exception as exc:
                    # Never disclose credentials in provider-generated messages.
                    st.error(str(exc).replace(image_key, "[API KEY ẨN]"))

        recognized = st.session_state.get(f"thumb_{sid}_ai_ocr")
        if isinstance(recognized, dict):
            st.markdown("**Chữ trên thumbnail và bản dịch đã nhận diện**")
            st.text_area(
                "Chữ gốc", value=recognized.get("original", ""),
                height=80, disabled=True, key=f"thumb_{sid}_ocr_original",
            )
            st.text_area(
                "Chữ đã dịch", value=recognized.get("translated", ""),
                height=80, disabled=True, key=f"thumb_{sid}_ocr_translated",
            )
        for mode, label in (
            ("recreate", "Thumbnail tạo lại"),
            ("translate", "Thumbnail đã dịch"),
        ):
            image_result = st.session_state.get(f"thumb_{sid}_ai_{mode}_png")
            if isinstance(image_result, bytes):
                st.image(image_result, caption=label, use_container_width=True)
                st.download_button(
                    f"⬇️ Tải {label} (PNG)", image_result,
                    file_name=f"thumbnail-{vid or 'custom'}-{mode}.png",
                    mime="image/png", use_container_width=True,
                    key=f"thumb_{sid}_download_ai_{mode}",
                )
        st.caption(
            "Ảnh AI không đảm bảo giống 100% hay viết chính xác mọi ký tự. "
            "Kết quả chỉ lưu trong phiên trình duyệt đang mở, không tự đồng bộ lên Supabase. "
            "Hãy tải PNG ngay sau khi tạo."
        )
