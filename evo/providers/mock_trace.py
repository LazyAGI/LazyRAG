from __future__ import annotations

import json
from pathlib import Path

from .trace_schema import normalize_trace


class MockTraceProvider:
    def __init__(self, fixture_path: Path | str) -> None:
        raw = json.loads(Path(fixture_path).read_text(encoding='utf-8'))
        if 'execution_tree' in raw and 'trace_id' in raw:
            self._index = {raw['trace_id']: raw}
        else:
            self._index = {v.get('trace_id') or k: v
                           for k, v in raw.items()
                           if isinstance(v, dict) and 'execution_tree' in v}

    def get_trace(self, trace_id: str) -> dict:
        if trace_id not in self._index:
            raise KeyError(f'trace {trace_id!r} not in mock fixture')
        return normalize_trace(self._index[trace_id])
