"""Targeted retries for one output section, preserving all other results.

Callers pass their already-configured generation functions. Mutation only
happens after valid results are available, avoiding partial overwrite on error.
"""
import hashlib

from character_images import character_specs
from video_scene_planner import character_bible_prompt, parse_json_object


def rerun_translation(session, target_language, translate):
    """Use previously optimized script, rather than raw transcript."""
    source = (session.get("optimized_script") or session.get("source") or "").strip()
    if not source:
        raise ValueError("Chưa có kịch bản gốc hoặc kịch bản tối ưu để dịch lại.")
    result = translate(source, target_language)
    if not isinstance(result, str) or not result.strip():
        raise ValueError("API trả bản dịch rỗng; giữ nguyên bản dịch trước.")
    previous = session.get("translated", "")
    session["translated"] = result.strip()
    if previous.strip() != result.strip():
        session["seo_stale"] = bool(
            session.get("new_title") or session.get("new_description") or session.get("seo_tags")
        )
        session["character_bible_stale"] = bool(session.get("character_bible"))
        # Do not destroy previous video prompts: their source hash will flag
        # them stale until the user uploads the correct voice audio to rerun.
    return result.strip()


def rerun_seo(session, language, make_metadata):
    target = session.get("translated", "").strip()
    if not target:
        raise ValueError("Chưa có bản dịch đích. Hãy chạy lại Bản dịch trước.")
    title, description, tags = make_metadata(
        target, session.get("title", ""), session.get("description", ""), language
    )
    if not all(isinstance(x, str) and x.strip() for x in (title, description, tags)):
        raise ValueError("API trả kết quả SEO thiếu thông tin; giữ nguyên kết quả cũ.")
    session.update({
        "new_title": title,
        "new_description": description,
        "seo_tags": tags,
        "metadata": "\n\n".join([title, description, tags]),
        "seo_stale": False,
    })
    return title, description, tags


def portrait_retry_specs(session, language, style, ai):
    """Reuse immutable character names where possible; do not edit video forms."""
    bible = session.get("character_bible", "").strip()
    if not session.get("translated", "").strip():
        raise ValueError("Cần hoàn thành bản dịch đích trước khi tạo lại ảnh.")
    if session.get("character_bible_stale") or not bible:
        data = parse_json_object(
            ai(character_bible_prompt(session["translated"], language, style)),
            "character_bible",
        )
        new_bible = data.get("character_bible")
        if not isinstance(new_bible, str) or not new_bible.strip():
            raise ValueError("AI chưa tạo được hồ sơ nhân vật.")
        return new_bible.strip(), character_specs(data), True
    specs = character_specs({"character_bible": bible})
    if not specs:
        # Request a strict extraction of structured identities, while
        # retaining the pre-existing character reference verbatim.
        data = parse_json_object(ai(
            "Extract all clearly identifiable recurring CHARACTERS from the "
            "provided character bible. Return JSON ONLY with characters "
            "array of objects {name,description}; do not invent any person. "
            "Include full costumes, colors, face/hair/body and species. "
            'Format: {"characters":[{"name":"...","description":"..."}]}.\n\n'
            + bible
        ), "characters")
        specs = character_specs(data)
    return bible, specs, False
