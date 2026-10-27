"""Provider fixture for tests that focus on writing/retry rather than arc ranking."""
import json


def whole_source_selection(prompt):
    parts = json.loads(prompt.split("SOURCE DATA:\n", 1)[1])["parts"]
    return json.dumps(dict(first_part=1, last_part=len(parts),
                           opening_quote=parts[0]["text"], ending_quote=parts[-1]["text"],
                           background_quotes=[], reason="Single coherent test story"))
