"""Process-local task registry for reconnecting Streamlit sessions after reload.

A worker keeps running if its original browser tab disconnects, as long as the
Streamlit Python process stays alive. The 128-bit random run ID is a bearer
capability in anonymous browser mode; authenticated tasks are also scoped to
the account. This is NOT a persistent queue and cannot survive server restart.
"""
import re
import threading
import time


class JobRegistry:
    """Keep Future/JobProgress alive outside the Streamlit session dictionary."""

    def __init__(self, keep_completed_seconds=24 * 3600):
        self._jobs = {}
        self._lock = threading.RLock()
        self._keep_completed_seconds = keep_completed_seconds

    def _purge_locked(self):
        now = time.monotonic()
        for run_id, item in list(self._jobs.items()):
            if item["future"].done():
                item.setdefault("finished_at", now)
                if now - item["finished_at"] > self._keep_completed_seconds:
                    del self._jobs[run_id]

    def register(self, run_id, session_id, scope, future, progress):
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Mã tác vụ không hợp lệ.")
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Mã phiên không hợp lệ.")
        if not isinstance(scope, str) or not scope:
            raise ValueError("Phạm vi phiên không hợp lệ.")
        with self._lock:
            self._purge_locked()
            if run_id in self._jobs:
                raise ValueError("Tác vụ đã tồn tại.")
            self._jobs[run_id] = {
                "run_id": run_id, "session_id": session_id, "scope": scope,
                "future": future, "progress": progress,
            }

    def lookup(self, run_id, session_id, scope):
        """Only return a job with the exact random run ID, session and owner."""
        if not isinstance(run_id, str):
            return None
        with self._lock:
            self._purge_locked()
            job = self._jobs.get(run_id)
            if job and job["session_id"] == session_id and job["scope"] == scope:
                return {
                    "run_id": run_id,
                    "future": job["future"],
                    "progress": job["progress"],
                }
        return None

    def cancel(self, run_id, session_id, scope):
        """Cancel/discard only an authorized job; prevent later reconnection."""
        if not isinstance(run_id, str):
            return False
        with self._lock:
            job = self._jobs.get(run_id)
            if not job or job["session_id"] != session_id or job["scope"] != scope:
                return False
            del self._jobs[run_id]
        job["progress"].cancel()
        job["future"].cancel()
        return True

    def discard(self, run_id, session_id, scope):
        """Release a finished job after results were saved into a workspace."""
        if not isinstance(run_id, str):
            return False
        with self._lock:
            job = self._jobs.get(run_id)
            if not job or job["session_id"] != session_id or job["scope"] != scope:
                return False
            if not job["future"].done():
                return False
            del self._jobs[run_id]
            return True
