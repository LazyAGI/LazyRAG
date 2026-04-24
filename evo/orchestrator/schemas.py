from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Op:
    op: str
    args: dict[str, Any] = field(default_factory=dict)
    rationale: str = ''


@dataclass
class OpResult:
    op: str
    status: str   # 'dispatched' | 'failed' | 'completed'
    summary: str = ''
    task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class TurnResult:
    thinking: str
    answer: str
    op_results: list[dict] = field(default_factory=list)
    interrupted: bool = False
