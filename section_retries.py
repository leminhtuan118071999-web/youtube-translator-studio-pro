"""Targeted retries for one output section, preserving all other results.

Callers pass their already-configured generation functions. Mutation only
happens after valid results are available, avoiding partial overwrite on error.
"""
import hashlib
import json

from faithful_summary import (
    optimize_source_script, COMPATIBLE_OPTIMIZATION_VERSIONS, source_hash, MAX_OPTIMIZED_SCRIPT_CHARS,
    rewrite_target_script,
)

from character_images import character_specs
from video_scene_planner import character_bible_prompt, parse_json_object


def prepare_reviewed_script(session, call, progress):
    """Return staged updates; do not overwrite a session if later translation fails."""
    original = (session.get("source") or "").strip()
    if not original:
        return {}
    optimized = session.get("optimized_script") or ""
    try:
        report = json.loads(session.get("optimization_review_json") or "{}")
    except (ValueError, TypeError):
        report = {}
    if (isinstance(report, dict) and report.get("version") in COMPATIBLE_OPTIMIZATION_VERSIONS
            and bool(optimized.strip()) and len(optimized) <= MAX_OPTIMIZED_SCRIPT_CHARS
            and report.get("source_sha256") == source_hash(original)
            and report.get("output_sha256") == source_hash(optimized)):
        return {}
    if session.get("optimization_work_json"):
        progress.publish("optimization_work_json", session["optimization_work_json"])
    optimized = optimize_source_script(original, call, progress)
    return {"optimized_script": optimized,
            "optimization_work_json": "",
            "optimization_review_json": progress.partial_result()["optimization_review_json"]}


def rerun_translation(session, target_language, translate, *, prepare=None):
    """Use previously optimized script, rather than raw transcript."""
    prepared = prepare(session) if prepare else {}
    source = (prepared.get("optimized_script") or session.get("optimized_script") or session.get("source") or "").strip()
    if not source:
        raise ValueError("Chưa có kịch bản gốc hoặc kịch bản tối ưu để dịch lại.")
    result = translate(source, target_language)
    if not isinstance(result, str) or not result.strip():
        raise ValueError("API trả bản dịch rỗng; giữ nguyên bản dịch trước.")
    previous = session.get("translated", "")
    session.update(prepared)
    session["translated"] = result.strip()
    if previous.strip() != result.strip():
        session["seo_stale"] = bool(
            session.get("new_title") or session.get("new_description") or session.get("seo_tags")
        )
        session["character_bible_stale"] = bool(session.get("character_bible"))
        # Do not destroy previous video prompts: their source hash will flag
        # them stale until the user uploads the correct voice audio to rerun.
    return result.strip()


def rerun_target_rewrite(session, target_language, call, progress):
    """Rebuild from the original; commit target text and review atomically."""
    original = (session.get("source") or "").strip()
    if not original:
        raise ValueError("Cần văn bản gốc để viết lại bản ngôn ngữ đích dưới 9.000 ký tự.")
    if session.get("optimization_work_json"):
        progress.publish("optimization_work_json", session["optimization_work_json"])
    result = rewrite_target_script(original, target_language, call, progress)
    previous = session.get("translated", "")
    session.update(translated=result, optimized_script=result, language=target_language,
                   optimization_work_json="",
                   optimization_review_json=progress.partial_result()["optimization_review_json"])
    if previous.strip() != result:
        session["seo_stale"] = bool(session.get("new_title") or session.get("new_description") or session.get("seo_tags"))
        session["character_bible_stale"] = bool(session.get("character_bible"))
    return result


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
