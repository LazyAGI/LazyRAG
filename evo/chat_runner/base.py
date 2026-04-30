from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
ChatRole = Literal['production', 'candidate', 'retired']
@dataclass
class ChatInstance:
    chat_id: str
    pid: int | None
    port: int
    base_url: str
    source_dir: Path
    health_url: str = ''
    status: str = 'starting'
    role: ChatRole = 'candidate'
    owner_thread_id: str | None = None
class ChatRunner(Protocol):
    def launch(self, *, source_dir: Path, label: str, env: dict | None=None, owner_thread_id: str | None=None) -> ChatInstance:
        ...
    def stop(self, chat_id: str) -> None:
        ...
