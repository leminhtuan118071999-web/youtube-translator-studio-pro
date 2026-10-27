"""Share exact profile names with scene generation without rewriting spoken text."""
import json
import unicodedata


def profile_names(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    rows = value.get("characters", []) if isinstance(value, dict) else []
    names = []
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if isinstance(name, str) and name.strip() and name.strip() not in names:
            names.append(name.strip())
    return names


def name_contract(names):
    if not names:
        return ""
    return ("\nCANONICAL CHARACTER NAMES: " + json.dumps(names, ensure_ascii=False) +
            "\nThese are the exact names from the detailed character profiles. For these identities, "
            "use the exact spelling, diacritics and full name in visual_prompt, image_prompt, "
            "wardrobe references and character speech_segments.speaker. Never translate, anglicize, "
            "abbreviate or invent aliases. Match identities using story context, never merge people. "
            "Only depict characters actually present. Other source characters may exist without detailed profiles. "
            "Keep spoken text, narration and subtitles VERBATIM even if they contain nicknames or kinship terms.\n")


def apply_name_lock(plan, names):
    if names != plan.get("canonical_character_names", []):
        for scene in plan.get("scenes", []):
            for key in ("visual_prompt", "image_prompt", "speech_segments", "transition_to_next"):
                scene.pop(key, None)
        plan.pop("wardrobe_reference", None)
    plan["canonical_character_names"] = list(names)


def validate_speaker_spelling(rows, names):
    def identity(text):
        return unicodedata.normalize("NFC", " ".join(text.split())).casefold()
    lookup = {identity(name): name for name in names}
    for row in rows:
        for segment in row.get("speech_segments", []):
            if segment.get("kind") == "character":
                speaker = segment.get("speaker", "")
                canonical = lookup.get(identity(speaker))
                if canonical and speaker != canonical:
                    raise ValueError("Tên người nói phải đúng hồ sơ: " + canonical)
