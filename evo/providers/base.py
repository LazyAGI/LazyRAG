from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

EvalReport = dict[str, Any]
StructuredTrace = dict[str, Any]


@runtime_checkable
class EvalProvider(Protocol):
    def get_eval_report(self, eval_id: str) -> EvalReport: ...

    def list_evals(self, *, kb_id: str | None = None) -> list[dict]: ...

    def run_eval(self, *, dataset_id: str, target_chat_url: str,
                 options: dict | None = None) -> EvalReport: ...


@runtime_checkable
class TraceProvider(Protocol):
    def get_trace(self, trace_id: str) -> StructuredTrace: ...
