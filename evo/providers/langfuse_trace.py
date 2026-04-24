from __future__ import annotations

import dataclasses

from .trace_schema import normalize_trace


class LangfuseTraceProvider:
    def __init__(self) -> None:
        from lazyllm.tracing.consume import get_single_trace
        self._fetch = get_single_trace

    def get_trace(self, trace_id: str) -> dict:
        return normalize_trace(dataclasses.asdict(self._fetch(trace_id)))
