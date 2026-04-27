from __future__ import annotations

import time
from typing import Any


class _Idempotency:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = __import__('threading').Lock()

    def _evict(self) -> None:
        now = time.time()
        stale = [k for k, (ts, _) in self._cache.items() if now - ts > 30.0]
        for k in stale:
            self._cache.pop(k, None)

    def get_or_run(self, key: str | None, run_fn) -> Any:
        if not key:
            return run_fn()
        with self._lock:
            self._evict()
            hit = self._cache.get(key)
            if hit is not None:
                return hit[1]
        value = run_fn()
        with self._lock:
            self._cache[key] = (time.time(), value)
        return value
