from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from evo.apply.runner import ApplyOptions
from evo.abtest import VerdictPolicy
from evo.chat_runner import ChatRegistry, ChatRunner
from evo.runtime.config import EvoConfig
from evo.service.core.store import FsStateStore
from evo.service.core import store as _store


@dataclass
class ExecCtx:
    store: FsStateStore
    cfg: EvoConfig
    is_cancelled: Callable[[str], bool]
    register_proc: Callable[[str, Any], None]
    chat_runner_factory: Callable[[], ChatRunner]
    chat_registry: ChatRegistry
    apply_opts: ApplyOptions | None
    abtest_policy: dict[str, VerdictPolicy]
    on_stop: Callable[[str, str | None], None]
    on_failure: Callable[[str, Exception], None]
    on_success: Callable[[str, str], None]
    pop_thread: Callable[[str], None]
    pop_procs: Callable[[str], None]

    def report_start(self, tid: str) -> None:
        cur = _store.get(self.store, tid)
        if cur and cur['status'] == 'queued':
            try:
                _store.transition(self.store, tid, 'start')
            except _store.StateError:
                pass

    def update_payload(self, tid: str, delta: dict) -> None:
        cur = _store.get(self.store, tid)
        if cur is None:
            return
        merged = {**(cur.get('payload') or {}), **delta}
        _store.patch(self.store, tid, payload=merged)

    def report_success(self, tid: str, final_action: str = 'finish') -> None:
        self.on_success(tid, final_action)


class CancelToken:
    def __init__(self, ctx: ExecCtx, tid: str) -> None:
        self._ctx = ctx
        self._tid = tid

    def requested(self) -> bool:
        return self._ctx.is_cancelled(self._tid)
