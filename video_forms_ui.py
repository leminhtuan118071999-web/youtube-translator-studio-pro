"""Streamlit UI for generating and editing 8-second video prompt forms.

Each scene inherits immutable translation wording, timing and a shared
character reference. No video rendering/voice synthesis is performed here.
"""
import json
import hashlib
import math
from io import BytesIO

import streamlit as st

from video_scene_planner import (
    narration_plan, character_bible_prompt, batch_prompt,
    parse_json_object, apply_ai_batch, source_fingerprint, plan_export_text,
    continuous_video_forms_text, grouped_video_forms,
)
from copy_buttons import copy_all_button
from voice_alignment import (whisper_word_timestamps, align_target_words,
    audio_aligned_plan, duration_weighted_plan, speech_statistics,
    TransientAudioAPIError, MAX_AUDIO_BYTES)


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
                       mark_processed, persist_and_rerun, alignment_api_key=""):
    """Independent voice-first prompt generation after translation."""
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
    st.caption("Bước 1: tải file giọng đọc của chính bản dịch này; "
               "Bước 2: nhấn Tạo form video 8 giây. Không tạo form tự động khi nhấn BẮT ĐẦU TẠO TOÀN BỘ.")
    upload = st.file_uploader(
        "🎧 Tải file giọng đọc cuối cùng (bắt buộc)",
        type=["mp3", "wav", "m4a", "ogg"],
        key=f"video_audio_{sid}",
    )
    seconds = None
    audio_error = False
    audio_hash = None
    if upload is not None:
        try:
            if upload.size > MAX_AUDIO_BYTES:
                raise ValueError("File trên 25 MB. Hãy nén hoặc chia nhỏ audio.")
            seconds = _audio_duration(upload)
            audio_hash = hashlib.sha256(upload.getvalue()).hexdigest()
            st.audio(upload)
            voice_stats = speech_statistics(translated, seconds)
            st.info(
                f"🎞️ Tự tính: {voice_stats['form_count']} form × 8 giây = "
                f"{voice_stats['video_duration_seconds']} giây. "
                f"Giọng đọc: {seconds:.2f} giây; "
                f"tốc độ trung bình {voice_stats['average_wpm']} từ/phút; "
                f"dư {voice_stats['padding_seconds']} giây ở cuối."
            )
        except (ValueError, TypeError, OSError) as exc:
            st.error(f"Không đọc được file giọng đọc: {exc}")
            audio_error = True
    else:
        st.info("Vui lòng tải giọng đọc đã hoàn chỉnh trước khi tạo form.")
    if alignment_api_key:
        st.caption(
            "✅ Có OpenAI API: khi bấm Tạo form, hệ thống phân tích từ được nói "
            "và mốc thời gian bằng Whisper để chia cảnh theo giọng đọc. "
            "Nội dung vẫn giữ nguyên bản dịch."
        )
    else:
        st.warning(
            "⚠️ Chưa có OpenAI API key dành cho phân tích audio. "
            "Ứng dụng chỉ căn theo tổng thời lượng và ước tính chia từ, "
            "chưa xác định được chính xác thời điểm từng câu. "
            "Hãy cấu hình OpenAI Images API key (cũng hỗ trợ Whisper) để căn tốt hơn."
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
    stale = plan is not None and (plan.get("source_hash") != source_hash
            or (audio_hash is not None and plan.get("audio_sha256") != audio_hash))
    if stale:
        st.warning(
            "Bản dịch, ngôn ngữ hoặc file giọng đọc đã thay đổi. "
            "Hãy tạo lại form theo audio mới."
        )
    cannot_generate = (
        audio_error or upload is None or not translated
        or bool(session.get("job_state") == "running")
    )
    generate_clicked = st.button(
        "🎬 Tạo form 8 giây theo giọng đọc",
        type="primary", key=f"create_video_forms_{sid}",
        disabled=cannot_generate,
    )
    retry_clicked = st.button(
        "🔄 Chạy lại riêng — Form video 8 giây",
        key=f"retry_video_forms_{sid}",
        disabled=cannot_generate or plan is None,
    )
    if generate_clicked or retry_clicked:
        if not api_key.strip():
            st.warning("Hãy nhập API key của nhà cung cấp AI trước khi tạo form.")
        else:
            try:
                with st.spinner("Đang đối chiếu giọng đọc và bản dịch, tạo 6 form đầu..."):
                    if alignment_api_key:
                        try:
                            stamped = whisper_word_timestamps(
                                upload.getvalue(), upload.name, alignment_api_key
                            )
                        except TransientAudioAPIError as exc:
                            # A temporary Whisper 502 is not evidence that the
                            # uploaded narration is invalid. Continue visibly
                            # in estimated mode rather than losing the whole job.
                            new_plan = duration_weighted_plan(
                                translated, language, seconds,
                            )
                            new_plan["alignment_warning"] = (
                                f"{exc} Đã chuyển sang chế độ ƯỚC TÍNH "
                                "theo độ dài giọng đọc và bản dịch; "
                                "chưa căn chính xác theo từng từ."
                            )
                        else:
                            positions, similarity = align_target_words(
                                translated, stamped, seconds
                            )
                            new_plan = audio_aligned_plan(
                                translated, language, seconds, positions
                            )
                            new_plan["voice_match_score"] = similarity
                            new_plan["speech_stats"] = speech_statistics(
                                translated, seconds, stamped,
                            )
                    else:
                        new_plan = duration_weighted_plan(
                            translated, language, seconds,
                        )
                    new_plan["audio_sha256"] = audio_hash
                    new_plan["audio_filename"] = upload.name
                    bible = session.get("character_bible", "")
                    if not bible.strip():
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
    if plan.get("alignment_warning"):
        st.warning(plan["alignment_warning"])
    st.caption(
        "Căn theo từng từ (Whisper, vẫn có sai số)" if plan.get("alignment_mode") == "whisper_word_timestamps"
        else "Căn ước tính theo tổng thời lượng file; chưa có timestamp từng từ."
    )
    if plan.get("voice_match_score") is not None:
        st.caption(f"Độ tương đồng giọng đọc/bản dịch: {plan['voice_match_score']:.0%}.")
    if plan.get("speech_stats"):
        stats = plan["speech_stats"]
        st.caption(
            f"Tự phân tích tốc độ: {stats['average_wpm']} từ/phút tính trên toàn audio."
            + (f" Tốc độ khi thực sự nói: {stats['speaking_wpm']} từ/phút."
               if stats.get('speaking_wpm') else "")
            + (f" Khoảng ngừng ước tính: {stats['silence_seconds']} giây."
               if stats.get('silence_seconds') is not None else "")
        )
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
    with st.expander("📌 Hồ sơ nhân vật/bối cảnh cố định cho mọi form", expanded=False):
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

    continuous_text = continuous_video_forms_text(plan)
    st.markdown("**📜 Tất cả form video — liền mạch**")
    st.caption(
        "Mỗi ô tối đa 99 form; mỗi ô mở/thu gọn và Copy toàn bộ độc lập. "
        "Các form cách nhau một dòng trống, giữ nguyên thứ tự và nội dung."
    )
    groups = grouped_video_forms(plan)
    if not groups:
        st.info("Chưa có form hoàn thành.")
    for group in groups:
        with st.expander(
            f"📜 Ô {group['panel']} — Form {group['first']:03d}–"
            f"{group['last']:03d} ({group['completed']} form đã tạo)",
            expanded=False,
        ):
            copy_all_button(
                f"📋 Copy toàn bộ ô {group['panel']}",
                group["content"],
                key=f"copy_all_video_forms_{sid}_{group['panel']}",
            )
            st.code(group["content"], language=None, wrap_lines=True)

    st.download_button(
        "⬇️ Tải tất cả form (.txt)", continuous_text,
        file_name=f"video-forms-{sid[:8]}.txt",
        mime="text/plain", key=f"download_video_forms_text_{sid}",
    )
    st.download_button(
        "⬇️ Tải JSON form video", session["video_forms"],
        file_name=f"video-forms-{sid[:8]}.json",
        mime="application/json", key=f"download_video_forms_json_{sid}",
    )

    # Individual per-scene editors, paging and copy buttons were intentionally
    # removed. Use the continuous overview and Copy all above.
