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
    narration_plan, character_bible_prompt, batch_prompt, InvalidFormJSON,
    parse_json_object, apply_ai_batch, source_fingerprint, plan_export_text,
    continuous_video_forms_text, grouped_video_forms, add_scene_subtitles, continuous_image_prompts_text, continuous_combined_forms_text,
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
    batch_size = 2 if plan.get("paired_prompts_required") else 3 if plan.get("speech_roles_required") else 6
    while _completed_count(plan) < len(plan["scenes"]):
        if progress:
            progress(plan, "🎬 Đang viết form video")
        try:
            written = _generate_batch(plan, ai, batch_size=batch_size)
        except (ProviderReadTimeout, InvalidFormJSON) as exc:
            pending_count = sum(not s.get("visual_prompt", "").strip() for s in plan["scenes"])
            attempted = min(batch_size, pending_count)
            if attempted <= 1:
                raise
            batch_size = max(1, attempted // 2)
            if progress:
                reason = "AI trả JSON lỗi" if isinstance(exc, InvalidFormJSON) else "API xử lý chậm"
                progress(plan, f"⏳ {reason}; tự giảm còn {batch_size} form/lượt")
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
    pass
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
    pass
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
    with st.expander("🔒 Khóa trang phục nhân vật", expanded=False):
        wardrobe_enabled = st.checkbox(
            "Giữ nguyên trang phục từ đầu đến cuối video",
            value=bool(session.get("wardrobe_lock_enabled", True)),
            key=f"wardrobe_enabled_{sid}", disabled=session.get("video_job_state") == "running",
        )
        wardrobe_notes = st.text_area(
            "Trang phục từng nhân vật (để trống để lấy từ hồ sơ)",
            value=str(session.get("wardrobe_lock_notes") or ""),
            placeholder="Quỳnh Anh: áo trắng, khăn quàng đỏ, váy xanh navy, giày đen.\nBà Thu: áo bà ba nâu, quần đen.",
            key=f"wardrobe_notes_{sid}", disabled=session.get("video_job_state") == "running",
        )
        if (session.get("wardrobe_lock_enabled", True) != wardrobe_enabled
                or session.get("wardrobe_lock_notes", "") != wardrobe_notes):
            session["wardrobe_lock_enabled"] = wardrobe_enabled
            session["wardrobe_lock_notes"] = wardrobe_notes
            persist_and_rerun()
        if raw_plan:
            try:
                locked = json.loads(raw_plan).get("wardrobe_reference", "")
                if locked:
                    st.code(locked, language=None, wrap_lines=True)
            except (ValueError, TypeError, AttributeError):
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
    stale = plan is not None and plan.get("source_hash") != source_hash
    if stale:
        st.warning(
            "Bản dịch hoặc ngôn ngữ đã thay đổi. "
            "Nhấn Tạo form 8 giây theo giọng đọc để tự đồng bộ."
        )
    cannot_generate = (
        not translated
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
                saved_plan = (plan if plan is not None and not stale
                              and _completed_count(plan) < len(plan["scenes"])
                              and plan.get("style") == style else None)
                launch_video_job(
                    (saved_plan.get("audio_duration_seconds") if saved_plan else None),
                    (saved_plan.get("audio_sha256") if saved_plan else ""),
                    (saved_plan.get("audio_filename", "") if saved_plan else ""),
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
            pass
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
    pass
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
    if plan.get("audio_duration_seconds") and plan.get("end_padding_seconds", 0) > 0:
        st.caption(
            f"Dự kiến dư {plan['end_padding_seconds']:.1f} giây ở cuối: "
            "phần hình dài hơn giọng đọc."
        )
    if done < len(scenes):
        st.info(
            f"Còn {len(scenes) - done} form chưa hoàn thành. "

        )

    pass
    continuous_text = continuous_combined_forms_text(plan)
    st.markdown("**📜 Tất cả form video — liền mạch**")
    pass
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
    image_text = continuous_image_prompts_text(plan)
    if image_text:
        st.download_button("⬇️ Tải tất cả prompt ảnh (.txt)", image_text,
                           file_name=f"image-prompts-{sid[:8]}.txt", mime="text/plain",
                           key=f"download_image_prompts_{sid}")
    st.download_button(
        "⬇️ Tải JSON form video", json.dumps(plan, ensure_ascii=False),
        file_name=f"video-forms-{sid[:8]}.json",
        mime="application/json", key=f"download_video_forms_json_{sid}",
    )

    # Individual per-scene editors, paging and copy buttons were intentionally
    # removed. Use the continuous overview and Copy all above.
