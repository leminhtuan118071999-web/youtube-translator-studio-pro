"""Streamlit UI for generating and editing 8-second video prompt forms.

Each scene inherits immutable translation wording, timing and a shared
character reference. No video rendering/voice synthesis is performed here.
"""
import json
import hashlib
import math
from io import BytesIO

import streamlit as st
from translation_language import saved_translation_language
from api_clients import ProviderReadTimeout

from video_scene_planner import (
    narration_plan, character_bible_prompt, batch_prompt,
    parse_json_object, apply_ai_batch, source_fingerprint, plan_export_text,
    continuous_video_forms_text, grouped_video_forms, add_scene_subtitles,
)
from copy_buttons import copy_all_button
from voice_alignment import duration_weighted_plan, speech_statistics, MAX_AUDIO_BYTES


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


def _completed_count(plan):
    return sum(bool(scene.get("visual_prompt", "").strip())
               for scene in plan.get("scenes", []))


def _progress_description(plan, stage):
    completed = _completed_count(plan)
    total = len(plan.get("scenes", []))
    percent = round(completed * 100 / total) if total else 0
    return completed, total, percent, f"{stage} • {completed}/{total} form ({percent}%)"


def _generate_batch(plan, ai, batch_size=6):
    """One atomic six-scene provider call, used internally by auto-completion."""
    pending = [s for s in plan["scenes"] if not s.get("visual_prompt", "").strip()][:batch_size]
    if not pending:
        return 0
    expected = [item["number"] for item in pending]
    answer = ai(batch_prompt(plan, pending, style=plan["style"]))
    apply_ai_batch(plan, answer, expected)
    return len(pending)


def _generate_all_remaining(plan, ai, *, progress=None, checkpoint=None):
    """Write ALL estimated scenes with one click; checkpoint each completed batch.

    Checkpoints happen only after an entire AI batch validates successfully.
    On provider errors, previously generated prompts remain intact.
    """
    batch_size = 3 if plan.get("speech_roles_required") else 6
    while _completed_count(plan) < len(plan["scenes"]):
        if progress:
            progress(plan, "🎬 Đang viết form video")
        try:
            written = _generate_batch(plan, ai, batch_size=batch_size)
        except ProviderReadTimeout:
            pending_count = sum(not s.get("visual_prompt", "").strip() for s in plan["scenes"])
            attempted = min(batch_size, pending_count)
            if attempted <= 1:
                raise
            batch_size = max(1, attempted // 2)
            if progress:
                progress(plan, f"⏳ API xử lý chậm; tự giảm còn {batch_size} form/lượt")
            continue
        if not written:
            raise RuntimeError("Không thể tiếp tục tạo form video.")
        if checkpoint:
            checkpoint(plan)
        if progress:
            progress(plan, "🎬 Đã hoàn thành nhóm form")
    return _completed_count(plan)


def render_video_forms(session, sid, language, *, ai, api_key,
                       mark_processed, persist_and_rerun, launch_video_job=None):
    """Independent voice-first prompt generation after translation."""
    language = saved_translation_language(session) or language
    st.subheader(f"🎬 Form video 8 giây — English · Lời đọc: {language}")
    st.caption(
        "Mỗi form là PROMPT tạo clip 8 giây, chưa xuất MP4. "
        "Lời đọc lấy nguyên văn từ BẢN DỊCH của đúng phiên và cùng ngôn ngữ đích. "
        "Giữa các clip dùng hiệu ứng chuyển cảnh 1 giây trong đoạn cuối của mỗi clip 8 giây."
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
    character_bible = str(session.get("character_bible") or "").strip()
    raw_plan = session.get("video_forms", "")
    if not character_bible and isinstance(raw_plan, str) and raw_plan:
        try:
            saved_plan = json.loads(raw_plan)
            if isinstance(saved_plan, dict):
                character_bible = str(saved_plan.get("character_bible") or "").strip()
        except (ValueError, TypeError):
            pass
    if character_bible:
        copy_all_button("📋 Copy hồ sơ nhân vật/bối cảnh cố định", character_bible,
                        key=f"copy_character_bible_{sid}")
    with st.expander("📌 Hồ sơ nhân vật/bối cảnh cố định cho mọi form", expanded=False):
        if character_bible:
            st.code(character_bible, language=None, wrap_lines=True)
        else:
            st.info("Chưa có hồ sơ nhân vật/bối cảnh cố định.")
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
                f"bản dịch {voice_stats['translated_word_count']} từ, "
                f"trung bình {voice_stats['words_per_8s']} từ/form; "
                f"tốc độ ước tính {voice_stats['average_wpm']} từ/phút; "
                f"dư {voice_stats['padding_seconds']} giây ở cuối."
            )
            if voice_stats["pacing_notice"]:
                st.warning(voice_stats["pacing_notice"])
        except (ValueError, TypeError, OSError) as exc:
            st.error(f"Không đọc được file giọng đọc: {exc}")
            audio_error = True
    else:
        pass
    plan = None
    if session.get("video_forms"):
        try:
            candidate = json.loads(session["video_forms"])
            if isinstance(candidate, dict) and isinstance(candidate.get("scenes"), list):
                plan = add_scene_subtitles(candidate)
        except (ValueError, TypeError):
            pass
    source_hash = source_fingerprint(translated, language)
    stale = plan is not None and (plan.get("source_hash") != source_hash
            or (audio_hash is not None and plan.get("audio_sha256") != audio_hash))
    if stale:
        st.warning(
            "Bản dịch, ngôn ngữ hoặc file giọng đọc đã thay đổi. "
            "Nhấn Tạo form 8 giây theo giọng đọc để tự đồng bộ."
        )
    saved_audio_available = bool(plan and plan.get("audio_duration_seconds"))
    cannot_generate = (
        audio_error or (upload is None and not saved_audio_available) or not translated
        or session.get("job_state") == "running"
        or session.get("video_job_state") == "running"
    )
    generate_clicked = st.button(
        "🎬 Tạo form 8 giây theo giọng đọc",
        type="primary", key=f"create_video_forms_{sid}",
        disabled=cannot_generate,
    )
    if generate_clicked:
        if not api_key.strip():
            st.warning("Hãy nhập API key của nhà cung cấp AI trước khi tạo form.")
        elif launch_video_job is None:
            st.error("Tác vụ tạo form trên máy chủ chưa được khởi tạo.")
        else:
            try:
                # Sending duration and translated text is sufficient. Do not
                # upload audio or call a speech transcription API.
                same_audio = plan is not None and (upload is None or plan.get("audio_sha256") == audio_hash)
                saved_plan = (plan if same_audio and _completed_count(plan) < len(plan["scenes"])
                              and plan.get("style") == style else None)
                if upload is None and saved_audio_available:
                    seconds = plan["audio_duration_seconds"]
                    audio_hash = plan.get("audio_sha256", "")
                    audio_name = plan.get("audio_filename", "speech")
                else:
                    audio_name = upload.name if upload is not None else "speech"
                launch_video_job(
                    (saved_plan.get("audio_duration_seconds") if saved_plan else seconds),
                    (saved_plan.get("audio_sha256") if saved_plan else audio_hash),
                    (saved_plan.get("audio_filename", "") if saved_plan else audio_name),
                    translated, language, style,
                    character_bible,
                    json.dumps(saved_plan, ensure_ascii=False) if saved_plan else None,
                )
            except (TypeError, ValueError, RuntimeError, KeyError) as exc:
                st.error(f"Không thể khởi động tạo form nền: {exc}")

    if session.get("video_job_state") == "running":
        pct = int(session.get("video_job_percent", 0) or 0)
        with st.expander(f"⏳ Đang tạo form · {min(100, max(0, pct))}%", expanded=False):
            st.progress(min(100, max(0, pct)), text=(
                f"⏳ Máy chủ đang viết form: {session.get('video_job_stage', 'Đang xử lý')}"
            ))
            st.caption(
                "Bạn có thể để máy tính ngủ hoặc đóng trình duyệt. "
                "Tác vụ vẫn chạy khi máy chủ còn hoạt động; nếu máy chủ "
                "khởi động lại thì cần tiếp tục từ kết quả đã lưu."
            )
    elif session.get("video_job_state") == "failed":
        st.warning(
            "Tác vụ tạo form bị gián đoạn: "
            + str(session.get("video_job_error", "Không rõ nguyên nhân."))
            + " Nhấn Tạo form 8 giây theo giọng đọc để tiếp tục những form còn thiếu."
        )
    if plan is not None and not stale:
        count, total, ratio, label = _progress_description(
            plan, "📊 Tiến trình tạo form"
        )
        st.progress(ratio, text=label)
    if plan is None or stale:
        return
    if plan.get("alignment_warning"):
        st.warning(plan["alignment_warning"])
    st.caption(
        "Căn ƯỚC TÍNH theo thời lượng file và độ dài bản dịch; "
        "không dùng nhận dạng lời nói hay timestamp từng từ."
    )
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
    if done < len(scenes):
        st.info(
            f"Còn {len(scenes) - done} form chưa hoàn thành. "
            "Nhấn '🔄 Chạy lại riêng — Form video 8 giây' ở trên "
            "để hệ thống tự tạo tiếp toàn bộ từ vị trí chưa xong."
        )

    st.caption("Phụ đề lấy từ lời đọc của từng form; thời điểm theo giọng đọc chỉ là ước tính.")
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
        "⬇️ Tải JSON form video", json.dumps(plan, ensure_ascii=False),
        file_name=f"video-forms-{sid[:8]}.json",
        mime="application/json", key=f"download_video_forms_json_{sid}",
    )

    # Individual per-scene editors, paging and copy buttons were intentionally
    # removed. Use the continuous overview and Copy all above.
