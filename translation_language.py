"""Resolve the language of the actual saved translation, not current controls."""
import json
from faithful_summary import source_hash


def saved_translation_language(record):
    text = record.get('translated') or ''
    if not text.strip():
        return None
    try:
        review = json.loads(record.get('optimization_review_json') or '{}')
        if (isinstance(review,dict) and review.get('output_sha256') == source_hash(text)
                and isinstance(review.get('target_language'),str) and review['target_language'].strip()):
            return review['target_language'].strip()
    except (ValueError,TypeError):
        pass
    try:
        plan = json.loads(record.get('video_forms') or '{}')
        if (isinstance(plan,dict) and plan.get('translation_sha256') == source_hash(text)
                and isinstance(plan.get('language'),str) and plan['language'].strip()):
            return plan['language'].strip()
    except (ValueError,TypeError):
        pass
    return None
