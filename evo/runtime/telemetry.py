from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Event], None]


@dataclass
class TelemetrySink:
    path: Path | None = None
    event_writer: Callable[[str, dict[str, Any]], None] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _subs: dict[str, list[Handler]] = field(default_factory=dict, repr=False)
    _history: list[Event] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def on(self, event_type: str, handler: Handler) -> None:
        self._subs.setdefault(event_type, []).append(handler)

    @property
    def history(self) -> list[Event]:
        with self._lock:
            return list(self._history)

    def emit(self, event_type: str, **payload: Any) -> None:
        ev = Event(type=event_type, payload=dict(payload))
        with self._lock:
            self._history.append(ev)
            if self.path is not None:
                rec = {'ts': _utc_now_iso(), 'type': event_type, **payload}
                line = json.dumps(rec, ensure_ascii=False, default=str)
                with open(self.path, 'a', encoding='utf-8') as fh:
                    fh.write(line + '\n')
            writer = self.event_writer
            handlers = list(self._subs.get(event_type, ())) + list(self._subs.get('*', ()))
        if writer is not None:
            try:
                writer(event_type, dict(payload))
            except Exception:
                pass
        for fn in handlers:
            try:
                fn(ev)
            except Exception:
                pass

    def as_callback(self) -> Callable[..., None]:
        return self.emit


__all__ = ['Event', 'Handler', 'TelemetrySink']
