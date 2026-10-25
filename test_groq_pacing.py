"""Bounded deterministic tests for the process-wide Groq TPM gate."""
import unittest
from groq_pacing import (
    GroqRequestGate, WINDOW_SECONDS, TPM_SOFT_BUDGET, estimated_tokens,
)


class FakeTime:
    def __init__(self):
        self.seconds = 0
        self.waits = []

    def clock(self):
        return self.seconds

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.seconds += seconds


class PacingTests(unittest.TestCase):
    def test_translation_requests_fit_below_8000_tokens_per_minute(self):
        prompt = "Dịch văn bản:\n" + "Some story sentence. " * 90
        self.assertLess(estimated_tokens(prompt), TPM_SOFT_BUDGET)
        self.assertGreater(estimated_tokens(prompt), 2200)

    def test_same_key_consecutive_requests_are_paced(self):
        t = FakeTime()
        gate = GroqRequestGate(clock=t.clock, sleeper=t.sleep)
        key = "never-store-plain-secret"
        prompt = "Dịch văn bản " + "a" * 2400
        cost = estimated_tokens(prompt)
        self.assertLess(2 * cost, TPM_SOFT_BUDGET)
        self.assertGreater(3 * cost, TPM_SOFT_BUDGET)
        gate.acquire(key, "openai/gpt-oss-120b", prompt)
        gate.acquire(key, "openai/gpt-oss-120b", prompt)
        self.assertEqual(t.seconds, 0)
        gate.acquire(key, "openai/gpt-oss-120b", prompt)
        self.assertGreaterEqual(t.seconds, WINDOW_SECONDS)
        self.assertNotIn(key, repr(gate._history))

    def test_different_keys_have_independent_budgets(self):
        t = FakeTime()
        gate = GroqRequestGate(clock=t.clock, sleeper=t.sleep)
        prompt = "Dịch " + "a" * 6000
        gate.acquire("key1", "openai/gpt-oss-120b", prompt)
        gate.acquire("key2", "openai/gpt-oss-120b", prompt)
        self.assertEqual(t.seconds, 0)

    def test_provider_429_cooldown_blocks_next_request(self):
        t = FakeTime()
        gate = GroqRequestGate(clock=t.clock, sleeper=t.sleep)
        gate.cooldown("key1", "gpt-oss", 12)
        gate.acquire("key1", "gpt-oss", "hello")
        self.assertGreaterEqual(t.seconds, 12)

    def test_cancellation_interrupts_long_wait(self):
        t = FakeTime()
        gate = GroqRequestGate(clock=t.clock, sleeper=t.sleep)
        class Progress:
            def __init__(self):
                self.checks = 0
            def check_cancelled(self):
                self.checks += 1
                if self.checks > 3:
                    raise RuntimeError("Canceled")
            def snapshot(self):
                return 0, "waiting"
            def update(self, percent, stage):
                pass
        gate.cooldown("key1", "model", 100)
        with self.assertRaisesRegex(RuntimeError, "Canceled"):
            gate.acquire("key1", "model", "hello", progress=Progress())
        self.assertLess(t.seconds, 10)


if __name__ == "__main__":
    unittest.main()
