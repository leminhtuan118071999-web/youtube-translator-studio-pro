"""Checkpoint detailed reference profiles before generating any video scenes."""
import hashlib
import json
from character_profiles import build_character_profiles
from character_identity import profile_names


def prepare_video_profiles(snapshot, call, publish, report):
    try:
        data = json.loads(snapshot.get("character_profile_json") or "{}")
        if not isinstance(data, dict):
            data = {}
    except (ValueError, TypeError):
        data = {}
    signature = hashlib.sha256(json.dumps(
        [snapshot["translated"], snapshot["language"], snapshot["style"]],
        ensure_ascii=False).encode()).hexdigest()
    if data.get("_video_profile_signature") == signature and data.get("character_bible"):
        return data
    work = data.get("_video_profile_build", {})
    names = work.get("canonical_names", profile_names(data)) if isinstance(work, dict) else profile_names(data)

    def checkpoint(state):
        partial = {"characters": state["sheets"],
                   "_video_profile_build": {"state": state, "canonical_names": names}}
        publish("character_profile_json", json.dumps(partial, ensure_ascii=False))

    result = build_character_profiles(
        snapshot["translated"], snapshot["language"], snapshot["style"], call,
        state=work.get("state") if isinstance(work, dict) else None,
        canonical_names=names, checkpoint=checkpoint, report=report,
    )
    result["_video_profile_signature"] = signature
    publish("character_profile_json", json.dumps(result, ensure_ascii=False))
    publish("character_bible", result["character_bible"])
    return result
