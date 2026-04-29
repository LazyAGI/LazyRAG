from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evo.service.core import store as _store
from evo.service.core.errors import StateError


@dataclass
class IntentPreview:
    op: str
    humanized: str
    safety: str
    params_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class Intent:
    intent_id: str
    thread_id: str
    user_message: str
    reply: str = ''
    suggested_ops_preview: list[IntentPreview] = field(default_factory=list)
    requires_confirm: bool = False
    thinking: str = ''
    trace: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class PlanResult:
    intent_id: str
    ops: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


class IntentStore:
    """Full FSM: pending_confirm -> confirmed -> materialized | cancelled | expired."""

    _TTL_S = 3600.0  # 1 hour expiry for pending intents

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, intent_id: str) -> Path:
        return self._base_dir / f'{intent_id}.json'

    def save(self, intent: Intent) -> None:
        data = {
            'intent_id': intent.intent_id,
            'thread_id': intent.thread_id,
            'user_message': intent.user_message,
            'reply': intent.reply,
            'suggested_ops_preview': [
                {'op': p.op, 'humanized': p.humanized, 'safety': p.safety,
                 'params_summary': p.params_summary}
                for p in intent.suggested_ops_preview
            ],
            'requires_confirm': intent.requires_confirm,
            'thinking': intent.thinking,
            'trace': intent.trace,
            'created_at': intent.created_at,
            'status': 'pending_confirm',
        }
        self._path(intent.intent_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def get(self, intent_id: str) -> dict | None:
        p = self._path(intent_id)
        if not p.exists():
            return None
        rec = json.loads(p.read_text(encoding='utf-8'))
        # Auto-expire check
        if rec.get('status') == 'pending_confirm':
            age = time.time() - rec.get('created_at', 0)
            if age > self._TTL_S:
                rec['status'] = 'expired'
                rec['updated_at'] = time.time()
                p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        return rec

    def transition(self, intent_id: str, action: str) -> dict:
        rec = self.get(intent_id)
        if rec is None:
            raise StateError('INTENT_NOT_FOUND', f'intent {intent_id} not found')
        current = rec.get('status', 'pending_confirm')
        if current == 'expired':
            raise StateError('INTENT_EXPIRED',
                             f'intent {intent_id} has expired (TTL={self._TTL_S}s)',
                             {'status': 'expired'})
        if current in ('cancelled', 'materialized'):
            raise StateError('INTENT_ALREADY_FINAL',
                             f'intent {intent_id} is already {current}',
                             {'current_status': current, 'action': action})
        transitions = {
            'pending_confirm': {'confirm': 'confirmed', 'cancel': 'cancelled'},
            'confirmed': {'materialize': 'materialized', 'cancel': 'cancelled'},
        }
        allowed = transitions.get(current, {})
        if action not in allowed:
            raise StateError('INTENT_ILLEGAL_TRANSITION',
                             f'intent {intent_id} is {current}, cannot {action}',
                             {'current_status': current, 'action': action,
                              'allowed': list(allowed)})
        rec['status'] = allowed[action]
        rec['updated_at'] = time.time()
        self._path(intent_id).write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        return rec

    def list_pending(self, thread_id: str) -> list[dict]:
        out: list[dict] = []
        for p in self._base_dir.glob('*.json'):
            rec = json.loads(p.read_text(encoding='utf-8'))
            if rec.get('thread_id') != thread_id:
                continue
            status = rec.get('status')
            if status in ('cancelled', 'materialized', 'expired'):
                continue
            # Check expiry inline for pending_confirm
            if status == 'pending_confirm':
                age = time.time() - rec.get('created_at', 0)
                if age > self._TTL_S:
                    rec['status'] = 'expired'
                    rec['updated_at'] = time.time()
                    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
                    continue
            out.append(rec)
        return out
