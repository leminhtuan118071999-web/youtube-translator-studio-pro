"""Tests for reconnection to process-local background work."""
import unittest
from concurrent.futures import Future
from unittest.mock import patch

from background_registry import JobRegistry
from background_jobs import JobProgress


RUN = "a" * 32
SESSION = "b" * 32


class JobRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry(keep_completed_seconds=5)
        self.future = Future()
        self.progress = JobProgress()
        self.registry.register(RUN, SESSION, "account:user-a", self.future, self.progress)

    def test_reconnect_when_original_tab_disappears(self):
        self.assertIs(
            self.registry.lookup(RUN, SESSION, "account:user-a")["future"],
            self.future,
        )
        self.progress.update(48, "Đang dịch phần 2")
        self.assertEqual(
            self.registry.lookup(RUN, SESSION, "account:user-a")["progress"].snapshot()[0],
            48,
        )
        self.future.set_result({"ok": True, "fields": {"translated": "Hello"}})
        self.assertTrue(
            self.registry.lookup(RUN, SESSION, "account:user-a")["future"].done()
        )
        self.assertTrue(self.registry.discard(RUN, SESSION, "account:user-a"))
        self.assertIsNone(self.registry.lookup(RUN, SESSION, "account:user-a"))

    def test_no_cross_user_or_cross_session_access(self):
        self.assertIsNone(self.registry.lookup(RUN, SESSION, "account:user-b"))
        self.assertIsNone(self.registry.lookup(RUN, "c" * 32, "account:user-a"))
        self.assertIsNone(self.registry.lookup("z" * 32, SESSION, "account:user-a"))
        self.assertFalse(self.registry.cancel(RUN, SESSION, "account:user-b"))
        self.assertFalse(self.registry.discard(RUN, SESSION, "account:user-a"))
        self.assertFalse(self.future.cancelled())

    def test_cancel_only_matching_session(self):
        self.assertTrue(self.registry.cancel(RUN, SESSION, "account:user-a"))
        self.assertIsNone(self.registry.lookup(RUN, SESSION, "account:user-a"))
        self.assertTrue(self.future.cancelled())
        with self.assertRaises(RuntimeError):
            self.progress.check_cancelled()

    def test_running_jobs_are_never_evicted_due_to_elapsed_time(self):
        with patch("background_registry.time.monotonic", return_value=123456):
            self.assertIsNotNone(self.registry.lookup(RUN, SESSION, "account:user-a"))
        with patch("background_registry.time.monotonic", return_value=999999):
            self.assertIsNotNone(self.registry.lookup(RUN, SESSION, "account:user-a"))

    def test_finished_results_expire_after_retention_period(self):
        self.future.set_result({"ok": True})
        with patch("background_registry.time.monotonic", return_value=10):
            self.assertIsNotNone(self.registry.lookup(RUN, SESSION, "account:user-a"))
        with patch("background_registry.time.monotonic", return_value=16):
            self.assertIsNone(self.registry.lookup(RUN, SESSION, "account:user-a"))

    def test_reject_duplicate_and_invalid_ids(self):
        with self.assertRaises(ValueError):
            self.registry.register(RUN, SESSION, "account:user-a", Future(), JobProgress())
        with self.assertRaises(ValueError):
            self.registry.register("bad-id", SESSION, "account:user-a", Future(), JobProgress())
        with self.assertRaises(ValueError):
            self.registry.register("c" * 32, SESSION, "", Future(), JobProgress())


if __name__ == "__main__":
    unittest.main()
