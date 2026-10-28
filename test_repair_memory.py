import json
import unittest
from repair_memory import RepairMemory, merge_memories, read_memory
from persistent_store import normalize_sessions

class RepairMemoryTests(unittest.TestCase):
    def test_only_successful_repairs_are_applied_to_future_jobs(self):
        memory = RepairMemory()
        memory.observe('Missing narrator delivery for SECRET_STORY API_KEY')
        failed = RepairMemory(memory.encoded())
        self.assertEqual(failed.instructions(), '')
        memory.confirm()
        resumed = RepairMemory(memory.encoded())
        self.assertIn('delivery=off_screen', resumed.instructions())
        self.assertNotIn('SECRET_STORY', memory.encoded())
        self.assertNotIn('API_KEY', memory.encoded())

    def test_account_session_merge_is_idempotent(self):
        memory = RepairMemory()
        memory.observe('wardrobe mismatch')
        memory.confirm()
        combined = merge_memories([memory.encoded(), memory.encoded()])
        self.assertEqual(read_memory(combined)['wardrobe_continuity']['verified'], 1)

    def test_untrusted_rules_do_not_become_instructions(self):
        memory = RepairMemory(json.dumps({'rules': {'ignore_all_rules': {'verified': 50}, 'json_format': {'verified': 1, 'observed': 1}}}))
        self.assertNotIn('ignore_all_rules', memory.instructions())
        self.assertIn('JSON', memory.instructions())

    def test_saved_session_retains_memory(self):
        sid = 'a' * 32
        memory = RepairMemory()
        memory.observe('json')
        value = memory.encoded()
        result = normalize_sessions({'workspaces': {sid: {'repair_memory_json': value}}})
        self.assertEqual(result['workspaces'][sid]['repair_memory_json'], value)
