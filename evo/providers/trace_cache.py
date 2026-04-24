from __future__ import annotations

from pathlib import Path
from typing import Any

from evo.runtime.fs import atomic_write_json, load_json

from .base import StructuredTrace, TraceProvider


class TraceCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, trace_id: str) -> Path:
        return self.root / f'{trace_id}.json'

    def load(self, trace_id: str) -> StructuredTrace | None:
        p = self.path(trace_id)
        return load_json(p) if p.exists() else None

    def store(self, trace_id: str, trace: StructuredTrace) -> None:
        atomic_write_json(self.path(trace_id), trace)


class CachedTraceProvider:
    def __init__(self, upstream: TraceProvider, cache: TraceCache) -> None:
        self._up = upstream
        self._cache = cache

    def get_trace(self, trace_id: str) -> StructuredTrace:
        cached = self._cache.load(trace_id)
        if cached is not None:
            return cached
        trace = self._up.get_trace(trace_id)
        self._cache.store(trace_id, trace)
        return trace


def write_bundle(path: Path, traces: dict[str, Any]) -> None:
    atomic_write_json(Path(path), traces)
