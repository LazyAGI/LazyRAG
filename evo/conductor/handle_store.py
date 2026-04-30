from __future__ import annotations
import itertools
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from evo.utils import jsonable
@dataclass(frozen=True)
class Handle:
    id: str
    tool: str
    args: dict[str, Any]
    result: Any
    ts: float
class HandleStore:
    def __init__(self, path: Path | None, event_writer: Callable[[str, dict[str, Any]], None] | None=None) -> None:
        self._path = path
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._event_writer = event_writer
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._cache: dict[str, Handle] = {}
    @property
    def path(self) -> Path | None:
        return self._path
    def append(self, tool: str, args: dict[str, Any], result: Any) -> str:
        with self._lock:
            h_id = f'h_{next(self._counter):04d}'
            h = Handle(h_id, tool, dict(args), result, time.time())
            self._cache[h_id] = h
            payload = {'h': h_id, 'ts': h.ts, 'tool': tool, 'args': jsonable(args), 'result': jsonable(result)}
            if self._path is not None:
                with self._path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + '\n')
            if self._event_writer is not None:
                self._event_writer('handle.created', payload)
            return h_id
    def get(self, h_id: str) -> Handle | None:
        return self._cache.get(h_id)
    def all(self) -> list[Handle]:
        return list(self._cache.values())
    def __len__(self) -> int:
        return len(self._cache)
