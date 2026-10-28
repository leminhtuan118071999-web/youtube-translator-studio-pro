"""Bounded, account-scoped repair lessons. Never persist model-authored instructions."""
import json

RULES = {
    "prop_continuity": "Removable props follow story actions, not wardrobe locks. Put-down bags stay down until picked up; retrieving an item does not mean wearing the bag.",
    "narrator_delivery": "Narrator always has delivery=off_screen; reported speech stays narration.",
    "character_delivery": "Every character segment has on_screen/off_screen/phone delivery grounded in context; callers never use listeners' mouths.",
    "identity_continuity": "Use exact canonical names and fixed profile appearance in every scene; never swap identities.",
    "wardrobe_continuity": "Repeat each present character's locked clothing in image and video; cultural garment names are not language errors.",
    "speech_coverage": "Preserve all source speech words, punctuation and order. Use one flat speech_segments list, without duplicates or nested segments.",
    "json_format": "Return one complete valid JSON object with escaped string content, no markdown.",
}


def read_memory(raw):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows = data.get("rules", {}) if isinstance(data, dict) else {}
        return {key: {field: min(10000, max(0, row.get(field, 0)))
                      for field in ("observed", "verified")
                      if type(row.get(field, 0)) is int}
                for key, row in rows.items() if key in RULES and isinstance(row, dict)}
    except (ValueError, TypeError, AttributeError):
        return {}


def merge_memories(values):
    merged = {}
    for value in values:
        for key, row in read_memory(value).items():
            current = merged.setdefault(key, {"observed": 0, "verified": 0})
            for field in current:
                current[field] = max(current[field], row.get(field, 0))
    return encode_memory(merged)


def encode_memory(rows):
    return json.dumps({"version": 1, "rules": rows}, sort_keys=True)


def classify_issue(issue):
    text = str(issue).casefold()
    keys = set()
    if "delivery" in text:
        keys.add("narrator_delivery" if "narrator" in text else "character_delivery")
    for key, terms in {
        "identity_continuity": ("identity", "name", "speaker", "face", "age", "hair"),
        "prop_continuity": ("backpack", "bag", "prop", "sets it down", "set down", "holding", "retrieval"),
        "wardrobe_continuity": ("wardrobe", "clothing", "outfit", "garment", "áo bà ba"),
        "speech_coverage": ("verbatim", "reported speech", "nested", "duplicate", "quotation"),
        "json_format": ("json",),
    }.items():
        if any(term in text for term in terms):
            keys.add(key)
    return keys


class RepairMemory:
    def __init__(self, raw=""):
        self.rows = read_memory(raw)
        self.pending = set()

    def observe(self, issue):
        for key in classify_issue(issue):
            row = self.rows.setdefault(key, {"observed": 0, "verified": 0})
            row["observed"] = min(10000, row.get("observed", 0) + 1)
            self.pending.add(key)

    def confirm(self):
        for key in self.pending:
            row = self.rows[key]
            row["verified"] = min(10000, row.get("verified", 0) + 1)
        self.pending.clear()

    def encoded(self):
        return encode_memory(self.rows)

    def instructions(self):
        # Only trusted, code-reviewed rules may become instructions. Unknown raw
        # provider error strings and story text are never carried to another job.
        keys = sorted((k for k in self.rows if self.rows[k].get("verified", 0) > 0 or k in self.pending), key=lambda k: (-self.rows[k].get("verified", 0), k))
        return ("\nPREVIOUS REPAIR LESSONS (apply only when relevant):\n" +
                "\n".join(RULES[key] for key in keys)) if keys else ""
