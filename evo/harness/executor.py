from __future__ import annotations
import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
class SessionAwareExecutor:
    def __init__(self, max_workers: int=4) -> None:
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
    def __enter__(self) -> 'SessionAwareExecutor':
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        return self
    def __exit__(self, *exc: Any) -> None:
        if self._executor:
            self._executor.shutdown(wait=True)
    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        assert self._executor is not None
        ctx = contextvars.copy_context()
        return self._executor.submit(lambda : ctx.run(fn, *args, **kwargs))
