"""The optional Thumbnail AI panel, independent of translation provider."""
import hashlib
import time

import streamlit as st

from thumbnail_ai import (
    GEMINI_IMAGE_MODELS, OPENAI_IMAGE_MODELS,
    normalize_thumbnail, recognize_and_translate, build_edit_prompt, edit_thumbnail,
)
from image_model_discovery import (
    discover_image_models, key_fingerprint, rank_image_models,
)


def image_provider_for_main_api(provider):
    """Only known official image-capable APIs may reuse the text API key."""
    return {"Google Gemini": "Gemini", "OpenAI": "OpenAI"}.get(provider)


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

        # Reuse the key already configured in the main multiprovider panel.
        # The selected text model can be different from the image model.
        main_provider = st.session_state.get("api_provider", "")
        shared_provider = image_provider_for_main_api(main_provider)
        if shared_provider:
            use_shared = st.checkbox(
                f"🔗 Dùng chung API Key {main_provider} trong Cấu hình API đa nền tảng",
                value=True, key=f"thumb_{sid}_ai_use_shared",
            )
            if use_shared:
                image_provider = shared_provider
                st.caption(
                    f"✅ Dùng chung API Key {main_provider} đã cấu hình. "
                    "Chỉ cần chọn model tạo ảnh phù hợp; không cần nhập lại khóa."
                )
            else:
                image_provider = st.selectbox(
                    "Dịch vụ chỉnh sửa ảnh riêng",
                    ["Gemini", "OpenAI"],
                    key=f"thumb_{sid}_image_provider",
                )
        else:
            use_shared = False
            st.info(
                "API đang chọn để dịch video không phải API chỉnh sửa ảnh "
                "Gemini/OpenAI. Vẫn giữ nguyên API dịch video; hãy chọn "
                "Gemini hoặc OpenAI cho phần Thumbnail AI."
            )
            image_provider = st.selectbox(
                "Dịch vụ chỉnh sửa ảnh",
                ["Gemini", "OpenAI"],
                key=f"thumb_{sid}_image_provider",
            )

        api_id = "Google Gemini" if image_provider == "Gemini" else "OpenAI"
        configured_key = str(st.session_state.get(f"api_key_{api_id}", "") or "").strip()
        try:
            secret_key = str(st.secrets.get(
                "GEMINI_API_KEY" if image_provider == "Gemini" else "OPENAI_API_KEY", ""
            ) or "").strip()
        except (FileNotFoundError, OSError, KeyError, AttributeError):
            secret_key = ""
        supplied_key = ""
        if not use_shared:
            supplied_key = st.text_input(
                "🔐 API Key chỉnh sửa ảnh (để trống nếu đã lưu Gemini/OpenAI trong cấu hình API)",
                type="password", key=f"thumb_{sid}_image_key_{image_provider}",
                help="Nhấn Enter hoặc rời khỏi ô sau khi nhập để tự nhận diện model.",
            )
        image_key = (
            configured_key or secret_key
            if use_shared else supplied_key.strip() or configured_key or secret_key
        )

        # Scan ONLY when a nonempty credential is committed, changed or the
        # user explicitly requests a refresh. Key fingerprints are hashed;
        # never save raw keys inside the scan record.
        discovery_id = f"thumb_{sid}_image_discovery_{image_provider}"
        discovered = st.session_state.get(discovery_id)
        fingerprint = key_fingerprint(image_provider, image_key) if image_key else None
        rescan = st.button(
            "🔎 Quét lại model ảnh",
            use_container_width=True,
            key=f"thumb_{sid}_image_rescan_{image_provider}",
            disabled=not bool(image_key),
        )
        scan_changed = (
            image_key and (
                not isinstance(discovered, dict)
                or discovered.get("fingerprint") != fingerprint
                or time.time() - discovered.get("checked_at", 0) > 1800
            )
        )
        if image_key and (scan_changed or rescan):
            with st.spinner("🔎 Đang tự nhận diện model tạo/sửa ảnh..."):
                try:
                    found = discover_image_models(image_provider, image_key)
                    discovered = {
                        "fingerprint": fingerprint,
                        "checked_at": time.time(),
                        "models": found,
                        "error": "",
                    }
                except Exception as exc:
                    # Discovery errors are intentionally generic and tokenless;
                    # still scrub the provided key before showing any message.
                    discovered = {
                        "fingerprint": fingerprint,
                        "checked_at": time.time(),
                        "models": [],
                        "error": str(exc).replace(image_key, "[API KEY ẨN]"),
                    }
                st.session_state[discovery_id] = discovered
        if not image_key:
            discovered = None
            st.session_state.pop(discovery_id, None)

        # A response from /models means the ID is visible, not that billing,
        # quotas, image editing or upload access has been granted.
        verified = (
            discovered.get("models", [])
            if isinstance(discovered, dict) and discovered.get("fingerprint") == fingerprint
            else []
        )
        known_models = GEMINI_IMAGE_MODELS if image_provider == "Gemini" else OPENAI_IMAGE_MODELS
        options = list(verified) if verified else list(known_models)
        model_widget = f"thumb_{sid}_image_model_{image_provider}"
        if st.session_state.get(model_widget) not in options:
            # First valid returned model is selected automatically, preserving
            # an existing manual choice if still present.
            st.session_state[model_widget] = options[0]
        image_model = st.selectbox(
            "Model tạo/sửa ảnh", options,
            key=model_widget,
        )
        if verified:
            st.success(
                f"✅ Tự nhận diện {len(verified)} model ảnh từ API. "
                f"Đã chọn: {image_model}. Có thể chọn model khác."
            )
            st.caption(
                "API liệt kê model thành công, nhưng quyền chỉnh sửa ảnh "
                "và hạn mức vẫn cần xác nhận khi tạo ảnh."
            )
        elif image_key and isinstance(discovered, dict) and discovered.get("error"):
            st.warning(
                discovered["error"] + " Đã hiển thị danh sách model gợi ý "
                "để bạn chọn thủ công; chưa xác nhận model khả dụng."
            )
        elif image_key and isinstance(discovered, dict):
            st.warning(
                "API không trả model chỉnh sửa ảnh được hỗ trợ. "
                "Các model hiển thị chỉ là lựa chọn thủ công; "
                "cần kiểm tra quyền và hạn mức nhà cung cấp."
            )
        else:
            st.caption(
                "Nhập API key rồi nhấn Enter hoặc rời ô nhập để tự quét model. "
                "Các lựa chọn hiện tại chưa được xác minh với tài khoản."
            )
        if not image_key:
            st.warning(
                f"Chưa có API Key {api_id} để tạo ảnh. "
                "Bạn có thể nhập trong Cấu hình API đa nền tảng."
            )
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
