"""Process-wide, per-Groq-key + model pacing to avoid 8K TPM bursts.

Rate limits belong to the Groq organization. Keys cannot be mapped reliably
to organizations, so this gate coordinates jobs sharing an API key on this
Streamlit server only. Provider 429 headers remain authoritative.
"""
from collections import deque
from contextlib import contextmanager
from hashlib import sha256
from threading import Lock, local
import time
from generation_budgets import task_output_budget


TPM_SOFT_BUDGET = 7200  # Headroom below observed Groq GPT-OSS 8K TPM
WINDOW_SECONDS = 65.0
MAX_RESERVATION = 6800


def estimated_tokens(prompt):
    """Conservative per-call reservation, including possible output tokens."""
    if task_output_budget(prompt) is not None:
        output = task_output_budget(prompt)
    elif "ĐÚNG 20 prompt" in prompt:
        output = 3600
    elif "Summarize" in prompt or "Condense" in prompt:
        output = 1400
    else:
        output = 2200
    return min(MAX_RESERVATION, max(500, len(prompt) // 2 + output + 150))


class GroqRequestGate:
    def __init__(self, clock=None, sleeper=None):
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = Lock()
        self._history = {}
        self._pause_until = {}
        self._thread_progress = local()

    @contextmanager
    def reporting(self, progress):
        """Route pacing status to the calling job, not another worker."""
        previous = getattr(self._thread_progress, "value", None)
        self._thread_progress.value = progress
        try:
            yield
        finally:
            self._thread_progress.value = previous

    @staticmethod
    def _id(key, model):
        # Never store plain API keys in a shared process-wide object.
        return sha256(key.encode("utf-8")).hexdigest(), model

    def acquire(self, key, model, prompt, progress=None):
        """Reserve a request without holding the lock while waiting."""
        progress = progress or getattr(self._thread_progress, "value", None)
        identity = self._id(key, model)
        cost = estimated_tokens(prompt)
        while True:
            if progress is not None:
                progress.check_cancelled()
            now = self._clock()
            with self._lock:
                history = self._history.setdefault(identity, deque())
                while history and now - history[0][0] >= WINDOW_SECONDS:
                    history.popleft()
                blocked = max(0.0, self._pause_until.get(identity, 0) - now)
                spent = sum(tokens for _, tokens in history)
                if blocked <= 0 and spent + cost <= TPM_SOFT_BUDGET:
                    history.append((now, cost))
                    return
                to_free = max(0, spent + cost - TPM_SOFT_BUDGET)
                release_delay = 0.0
                if to_free > 0:
                    released = 0
                    for used_at, tokens in history:
                        released += tokens
                        if released >= to_free:
                            release_delay = max(
                                0.0, WINDOW_SECONDS - (now - used_at)
                            )
                            break
                wait = max(0.25, blocked, release_delay)
            if progress is not None:
                percent, _ = progress.snapshot()
                progress.update(
                    percent,
                    f"⏳ Đang điều tiết Groq 8.000 token/phút: chờ "
                    f"{int(wait + 0.999)} giây..."
                )
            self._sleep(min(1.0, wait))

    def cooldown(self, key, model, seconds):
        """Share a provider-mandated retry delay with concurrent jobs."""
        identity = self._id(key, model)
        with self._lock:
            until = self._clock() + min(300.0, max(0.0, float(seconds)))
            self._pause_until[identity] = max(
                self._pause_until.get(identity, 0), until
            )


groq_request_gate = GroqRequestGate()
