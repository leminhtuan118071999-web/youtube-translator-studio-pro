"""Streamlit UI for generating and editing 8-second video prompt forms.

Each scene inherits immutable translation wording, timing and a shared
character reference. No video rendering/voice synthesis is performed here.
"""
import json
from io import BytesIO

import streamlit as st

from video_scene_planner import (
    narration_plan, character_bible_prompt, batch_prompt,
    parse_json_object, apply_ai_batch, source_fingerprint, plan_export_text,
    continuous_video_forms_text,
)
from copy_buttons import copy_all_button


def _audio_duration(file):
    """Read common voice-over file metadata without uploading to an AI vendor."""
    from mutagen import File
    audio = File(BytesIO(file.getvalue()))
    if audio is None or getattr(audio, "info", None) is None:
        raise ValueError("Không nhận dạng được định dạng file âm thanh.")
    seconds = float(audio.info.length)
    if not 0 < seconds < 86400:
        raise ValueError("Thời lượng giọng đọc không hợp lệ.")
    return seconds


def _generate_batch(plan, ai):
    pending = [s for s in plan["scenes"] if not s.get("visual_prompt", "").strip()][:6]
    if not pending:
        return 0
    expected = [item["number"] for item in pending]
    answer = ai(batch_prompt(plan, pending, style=plan["style"]))
    apply_ai_batch(plan, answer, expected)
    return len(pending)


def render_video_forms(session, sid, language, *, ai, api_key,
                       mark_processed, persist_and_rerun):
    """On-demand, session-scoped 8s storyboards alongside Translation and SEO."""
    st.subheader(f"🎬 Form video 8 giây — {language}")
    st.caption(
        "Mỗi form là PROMPT tạo clip 8 giây, chưa xuất MP4. "
        "Lời đọc lấy nguyên văn từ BẢN DỊCH của đúng phiên và cùng ngôn ngữ đích. "
        "Giữa các clip dùng hiệu ứng chuyển cảnh 0,4 giây nằm trong 8 giây."
    )
    translated = session.get("translated", "").strip()
    if not translated:
        st.warning("Hãy tạo bản dịch ngôn ngữ đích trước khi viết form video.")
        return

    style = st.selectbox(
        "🎨 Phong cách chung cho nhân vật và bối cảnh",
        ("Điện ảnh chân thực", "Hoạt hình 2D", "Hoạt hình 3D",
         "Phim tài liệu thiên nhiên"),
        key=f"video_style_{sid}",
    )
    wpm = st.slider(
        "🎙️ Tốc độ đọc ước tính (từ/phút) nếu chưa có audio",
        min_value=80, max_value=220, value=135, step=5,
        key=f"video_wpm_{sid}",
    )
    upload = st.file_uploader(
        "🎧 Tải MP3 / WAV / M4A / OGG giọng đọc để tính số form (không bắt buộc)",
        type=["mp3", "wav", "m4a", "ogg"],
        key=f"video_audio_{sid}",
    )
    seconds = None
    audio_error = False
    if upload is not None:
        try:
            seconds = _audio_duration(upload)
            st.caption(f"Thời lượng giọng đọc: {seconds:.1f} giây.")
        except (ValueError, TypeError, OSError) as exc:
            st.error(f"Không đọc được file giọng đọc: {exc}")
            audio_error = True
    st.caption(
        "⚠️ Dù đọc được tổng thời lượng âm thanh, cách chia lời theo từng form "
        "vẫn là ƯỚC TÍNH. Để tiếng khớp từng giây/từng từ cần timestamp hoặc "
        "forced alignment với chính file giọng đọc khi dựng video."
    )
    plan = None
    if session.get("video_forms"):
        try:
            candidate = json.loads(session["video_forms"])
            if isinstance(candidate, dict) and isinstance(candidate.get("scenes"), list):
                plan = candidate
        except (ValueError, TypeError):
            pass
    source_hash = source_fingerprint(translated, language)
    stale = plan is not None and plan.get("source_hash") != source_hash
    if stale:
        st.warning(
            "Bản dịch/ngôn ngữ đã thay đổi. Form cũ không còn khớp lời đọc. "
            "Hãy tạo lại các form từ bản dịch mới."
        )
    if st.button(
        "🎬 Tạo form video 8 giây từ bản dịch",
        type="primary", key=f"create_video_forms_{sid}",
        disabled=audio_error,
    ):
        if not api_key.strip():
            st.warning("Hãy nhập API key của nhà cung cấp AI trước khi tạo form.")
        else:
            try:
                with st.spinner("Đang xây dựng nhân vật và 6 form đầu..."):
                    new_plan = narration_plan(
                        translated, language, words_per_minute=wpm,
                        audio_duration_seconds=seconds,
                    )
                    result = parse_json_object(
                        ai(character_bible_prompt(translated, language, style)),
                        "character_bible",
                    )
                    bible = result["character_bible"]
                    if not isinstance(bible, str) or not bible.strip():
                        raise ValueError("AI chưa tạo được hồ sơ nhân vật.")
                    new_plan["character_bible"] = bible.strip()
                    new_plan["style"] = style
                    _generate_batch(new_plan, ai)
                    encoded = json.dumps(new_plan, ensure_ascii=False)
                    if len(encoded) > 390000:
                        raise ValueError("Form quá lớn để tự lưu; hãy chia nội dung.")
                    session["video_forms"] = encoded
                    mark_processed(session)
                    for widget_key in list(st.session_state):
                        if widget_key.startswith((
                            f"video_prompt_{sid}_", f"video_transition_{sid}_"
                        )):
                            st.session_state.pop(widget_key, None)
                    persist_and_rerun()
            except (TypeError, ValueError, RuntimeError, KeyError) as exc:
                st.error(f"Không thể tạo form video: {exc}")

    if plan is None or stale:
        return
    scenes = plan["scenes"]
    done = sum(bool(scene.get("visual_prompt", "").strip()) for scene in scenes)
    st.success(
        f"Đã viết {done}/{len(scenes)} form • mỗi form 8 giây • "
        f"tổng thời lượng dự kiến: {len(scenes) * 8} giây."
    )
    if plan.get("end_padding_seconds", 0) > 0:
        st.caption(
            f"Dự kiến dư {plan['end_padding_seconds']:.1f} giây ở cuối: "
            "cần giữ hình hoặc điều chỉnh nhịp khi ghép audio thật."
        )
    st.markdown("**📌 Hồ sơ nhân vật/bối cảnh cố định cho mọi form**")
    st.code(plan.get("character_bible", ""), language=None, wrap_lines=True)
    if done < len(scenes) and st.button(
        "▶️ Tạo tiếp 6 form còn thiếu", key=f"continue_video_forms_{sid}"
    ):
        if not api_key.strip():
            st.warning("Hãy nhập API key trước khi tiếp tục.")
        else:
            try:
                with st.spinner("Đang tạo form tiếp theo..."):
                    _generate_batch(plan, ai)
                    encoded = json.dumps(plan, ensure_ascii=False)
                    if len(encoded) > 390000:
                        raise ValueError("Form quá lớn để tự lưu.")
                    session["video_forms"] = encoded
                    mark_processed(session)
                    persist_and_rerun()
            except (TypeError, ValueError, RuntimeError, KeyError) as exc:
                st.error(f"Không thể tạo các form tiếp theo: {exc}")

    st.markdown("**📜 Tất cả form video — liền mạch**")
    st.caption(
        "Các form đã viết được nối theo đúng thứ tự: hết một form xuống "
        "dòng để bắt đầu form tiếp theo. Nút Copy toàn bộ sao chép "
        "cả lời đọc, prompt và chuyển cảnh, không cần mở từng form."
    )
    continuous_text = continuous_video_forms_text(plan)
    copy_all_button(
        "📋 Copy toàn bộ form",
        continuous_text,
        key=f"copy_all_video_forms_{sid}",
    )
    st.code(
        continuous_text if continuous_text else "Chưa có form hoàn thành.",
        language=None, wrap_lines=True,
    )

    st.download_button(
        "⬇️ Tải tất cả form (.txt)", plan_export_text(plan),
        file_name=f"video-forms-{sid[:8]}.txt",
        mime="text/plain", key=f"download_video_forms_text_{sid}",
    )
    st.download_button(
        "⬇️ Tải JSON form video", session["video_forms"],
        file_name=f"video-forms-{sid[:8]}.json",
        mime="application/json", key=f"download_video_forms_json_{sid}",
    )
    start = st.number_input(
        "Xem từ form số", min_value=1, max_value=max(1, len(scenes)),
        value=1, step=6, key=f"video_form_page_{sid}",
    )
    changed = False
    for scene in scenes[int(start) - 1:int(start) + 5]:
        n = scene["number"]
        with st.expander(
            f"🎞️ Form {n:03d} — "
            f"{scene['start_seconds']}-{scene['end_seconds']}s (8 giây)",
            expanded=n == int(start),
        ):
            st.caption(f"🎙️ Lời đọc nguyên bản ({language}) — không tự sửa:")
            st.code(scene["voiceover"], language=None, wrap_lines=True)
            edited = st.text_area(
                f"Prompt cảnh {n:03d}", value=scene.get("visual_prompt", ""),
                height=230, key=f"video_prompt_{sid}_{n}",
            )
            if edited != scene.get("visual_prompt", ""):
                scene["visual_prompt"] = edited
                changed = True
            transition = st.text_input(
                f"Hiệu ứng chuyển sang form {n+1}" if n < len(scenes)
                else "Kết thúc (không có chuyển cảnh)",
                value=scene.get("transition_to_next", ""),
                disabled=n == len(scenes),
                key=f"video_transition_{sid}_{n}",
            )
            if n < len(scenes) and transition != scene.get("transition_to_next", ""):
                scene["transition_to_next"] = transition
                changed = True
            copy_all_button(
                f"📋 Copy prompt form {n:03d}",
                scene.get("visual_prompt", ""), key=f"copy_video_form_{sid}_{n}",
            )
    if changed:
        encoded = json.dumps(plan, ensure_ascii=False)
        if len(encoded) <= 390000:
            session["video_forms"] = encoded
        else:
            st.error("Form quá lớn để tự lưu; hãy rút ngắn nội dung chỉnh sửa.")
