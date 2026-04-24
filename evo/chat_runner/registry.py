from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path

from evo.runtime.fs import atomic_write as _atomic_write

from .base import ChatInstance, ChatRole

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _pid_alive(pid: int | None) -> bool:
    if not pid or not _HAS_PSUTIL:
        return True
    return psutil.pid_exists(pid)


class ChatRegistry:
    def __init__(self, base_dir: Path | str) -> None:
        self.dir = Path(base_dir) / 'state' / 'chats'
        self.dir.mkdir(parents=True, exist_ok=True)
        self._guard = threading.RLock()

    def _path(self, chat_id: str) -> Path:
        return self.dir / f'{chat_id}.json'

    def register(self, instance: ChatInstance) -> ChatInstance:
        with self._guard:
            payload = dataclasses.asdict(instance)
            payload['source_dir'] = str(instance.source_dir)
            _atomic_write(self._path(instance.chat_id),
                          json.dumps(payload, ensure_ascii=False, indent=2,
                                     default=str))
        return instance

    def get(self, chat_id: str) -> ChatInstance | None:
        path = self._path(chat_id)
        if not path.exists():
            return None
        return _validate(_from_dict(json.loads(path.read_text(encoding='utf-8'))))

    def list(self, role: ChatRole | None = None) -> list[ChatInstance]:
        out = []
        for path in sorted(self.dir.glob('*.json')):
            inst = _validate(_from_dict(json.loads(path.read_text(encoding='utf-8'))))
            if role is None or inst.role == role:
                out.append(inst)
        return out

    def update(self, chat_id: str, **fields) -> ChatInstance:
        with self._guard:
            inst = self.get(chat_id)
            if inst is None:
                raise KeyError(chat_id)
            for k, v in fields.items():
                if not hasattr(inst, k):
                    raise ValueError(f'unknown field {k}')
                setattr(inst, k, v)
            self.register(inst)
            return inst

    def purge(self, chat_id: str) -> None:
        with self._guard:
            path = self._path(chat_id)
            if path.exists():
                path.unlink()


def _from_dict(data: dict) -> ChatInstance:
    data = dict(data)
    data['source_dir'] = Path(data.get('source_dir', '.'))
    return ChatInstance(**data)


def _validate(inst: ChatInstance) -> ChatInstance:
    if inst.status != 'stopped' and not _pid_alive(inst.pid):
        inst.status = 'unhealthy'
    return inst
