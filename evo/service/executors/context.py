from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable

from evo.apply.runner import ApplyOptions
from evo.abtest import VerdictPolicy
from evo.chat_runner import ChatRegistry, ChatRunner
from evo.providers import EvalProvider, TraceProvider
from evo.runtime.config import EvoConfig
from evo.service import state


@dataclass
class ExecCtx:
    store: state.FsStateStore
    cfg: EvoConfig
    is_cancelled: Callable[[str], bool]
    register_proc: Callable[[str, subprocess.Popen], None]
    eval_provider_factory: Callable[[], EvalProvider]
    trace_provider_factory: Callable[[], TraceProvider]
    chat_runner_factory: Callable[[], ChatRunner]
    chat_registry: ChatRegistry
    apply_opts: ApplyOptions | None
    abtest_policy: dict[str, VerdictPolicy]
    on_stop: Callable[[str, str | None], None]
    on_failure: Callable[[str, Exception], None]
    on_success: Callable[[str], None]
    pop_thread: Callable[[str], None]
    pop_procs: Callable[[str], None]


class CancelToken:
    def __init__(self, ctx: ExecCtx, tid: str) -> None:
        self._ctx = ctx
        self._tid = tid

    def requested(self) -> bool:
        return self._ctx.is_cancelled(self._tid)
