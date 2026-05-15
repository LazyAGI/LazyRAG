from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from evo.runtime.fs import atomic_write_json
from evo.service.core import store
THREAD_IDLE = 'idle'
THREAD_RUNNING = 'running'
THREAD_WAITING = 'waiting_user'
THREAD_PAUSED = 'paused'
THREAD_FAILED = 'failed'
THREAD_CANCELLED = 'cancelled'
THREAD_SUCCEEDED = 'succeeded'
ACTIVE_TASK_STATUSES = {'queued', 'running'}
RESUMABLE_TASK_STATUSES = {'paused', 'failed_transient'}
SUCCESS_TASK_STATUSES = {'succeeded', 'accepted'}
FAILED_TASK_STATUSES = {'failed_permanent', 'failed_transient', 'rejected'}


@dataclass
class ThreadRecord:
    id: str
    state: str = THREAD_IDLE
    current_flow: str | None = None
    active_task_id: str | None = None
    checkpoint: dict | None = None
    error: dict | None = None
    updated_at: float = 0.0

    def as_meta_patch(self) -> dict[str, Any]:
        return {
            'state': self.state,
            'current_flow': self.current_flow,
            'active_task_id': self.active_task_id,
            'checkpoint': self.checkpoint,
            'error': self.error,
            'updated_at': self.updated_at or time.time(),
        }


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def load_thread(base_dir: Path, thread_id: str, task_rows: list[dict] | None = None) -> ThreadRecord:
    thread_dir = base_dir / 'state' / 'threads' / thread_id
    meta = read_json(thread_dir / 'thread.json') or {}
    rows = task_rows or []
    if (thread_dir / 'cancelled.json').exists():
        return ThreadRecord(id=thread_id, state=THREAD_CANCELLED, updated_at=float(meta.get('updated_at') or 0.0))
    active = [r for r in rows if is_task_executing(r)]
    if active and meta.get('state') != THREAD_CANCELLED:
        task = active[-1]
        return ThreadRecord(thread_id, THREAD_RUNNING, task.get('flow'), task.get('id'), None, None, time.time())
    if meta.get('state') == THREAD_RUNNING:
        return derive_from_legacy(base_dir, thread_id, rows)
    checkpoint = meta.get('checkpoint') if isinstance(meta.get('checkpoint'), dict) else _pending_checkpoint(thread_dir)
    if _is_terminal_checkpoint(checkpoint):
        return ThreadRecord(
            id=thread_id,
            state=THREAD_SUCCEEDED,
            current_flow=checkpoint.get('completed_flow') or meta.get('current_flow'),
            checkpoint=checkpoint,
            updated_at=float(meta.get('updated_at') or 0.0),
        )
    if meta.get('state'):
        return ThreadRecord(
            id=thread_id,
            state=str(meta.get('state') or THREAD_IDLE),
            current_flow=meta.get('current_flow'),
            active_task_id=meta.get('active_task_id'),
            checkpoint=checkpoint,
            error=meta.get('error') if isinstance(meta.get('error'), dict) else None,
            updated_at=float(meta.get('updated_at') or 0.0),
        )
    if meta.get('status') in {'cancelled', 'failed', 'paused', 'completed'}:
        return ThreadRecord(
            id=thread_id,
            state={
                'cancelled': THREAD_CANCELLED,
                'failed': THREAD_FAILED,
                'paused': THREAD_PAUSED,
                'completed': THREAD_SUCCEEDED,
            }[str(meta['status'])],
            updated_at=float(meta.get('updated_at') or 0.0),
        )
    return derive_from_legacy(base_dir, thread_id, rows)


def save_thread(base_dir: Path, record: ThreadRecord) -> None:
    path = base_dir / 'state' / 'threads' / record.id / 'thread.json'
    meta = read_json(path) or {'id': record.id, 'mode': 'interactive', 'title': '', 'inputs': {}}
    meta.update(record.as_meta_patch())
    meta['status'] = project_thread_meta_status(record)
    atomic_write_json(path, meta)
    if record.state == THREAD_CANCELLED:
        atomic_write_json(path.parent / 'cancelled.json', {'status': 'cancelled', 'updated_at': meta['updated_at']})
    else:
        (path.parent / 'cancelled.json').unlink(missing_ok=True)
    if record.checkpoint:
        checkpoint = {'status': 'pending', **record.checkpoint}
        meta['checkpoint'] = checkpoint
        atomic_write_json(path, meta)
        atomic_write_json(base_dir / 'state' / 'threads' / record.id / 'checkpoint.json', checkpoint)
    else:
        atomic_write_json(path.parent / 'checkpoint.json', {'status': 'cleared', 'updated_at': meta['updated_at']})


def derive_from_legacy(base_dir: Path, thread_id: str, rows: list[dict]) -> ThreadRecord:
    thread_dir = base_dir / 'state' / 'threads' / thread_id
    checkpoint = _pending_checkpoint(thread_dir)
    runtime = read_json(thread_dir / 'runtime.json') or {}
    active = [r for r in rows if is_task_executing(r)]
    latest = rows[-1] if rows else None
    now = time.time()
    if runtime.get('status') == THREAD_CANCELLED or (latest or {}).get('status') == 'cancelled':
        return ThreadRecord(thread_id, THREAD_CANCELLED, _flow(latest), None, None, _error(latest), now)
    if runtime.get('status') == THREAD_PAUSED or (latest or {}).get('status') == 'paused':
        return ThreadRecord(thread_id, THREAD_PAUSED, _flow(latest), (latest or {}).get('id'), checkpoint, None, now)
    if active:
        task = active[-1]
        return ThreadRecord(thread_id, THREAD_RUNNING, task.get('flow'), task.get('id'), checkpoint, None, now)
    if runtime.get('status') == THREAD_FAILED or ((latest or {}).get('status') in FAILED_TASK_STATUSES):
        return ThreadRecord(
            thread_id,
            THREAD_FAILED,
            _flow(latest),
            (latest or {}).get('id'),
            checkpoint,
            _error(latest),
            now)
    if _is_terminal_checkpoint(checkpoint) or runtime.get('status') == 'ended':
        return ThreadRecord(thread_id, THREAD_SUCCEEDED, _flow(latest), None, checkpoint, None, now)
    if checkpoint:
        return ThreadRecord(thread_id, THREAD_WAITING, checkpoint.get(
            'completed_flow') or _flow(latest), None, checkpoint, None, now)
    return ThreadRecord(thread_id, THREAD_IDLE, _flow(latest), None, None, None, now)


def project_flow_status(record: ThreadRecord, rows: list[dict], report_ready: bool = False) -> dict:
    latest_abtest = latest_task(rows, 'abtest')
    return {
        'thread_id': record.id,
        'status': _public_flow_status(record),
        'active_task_ids': [r['id'] for r in rows if is_task_executing(r) and r.get('id')],
        'latest_abtest_id': latest_abtest.get('id') if latest_abtest else None,
        'latest_abtest_status': latest_abtest.get('status') if latest_abtest else None,
        'report_ready': report_ready,
        'pending_checkpoint': record.checkpoint if record.state == THREAD_WAITING else None,
    }


def project_thread_meta_status(record: ThreadRecord) -> str:
    return {
        THREAD_IDLE: 'active',
        THREAD_RUNNING: 'active',
        THREAD_WAITING: 'active',
        THREAD_PAUSED: 'paused',
        THREAD_FAILED: 'failed',
        THREAD_CANCELLED: 'cancelled',
        THREAD_SUCCEEDED: 'completed',
    }.get(record.state, 'active')


def latest_task(rows: list[dict], flow: str) -> dict | None:
    for row in reversed(rows):
        if row.get('flow') == flow:
            return row
    return None


def is_task_executing(row: dict) -> bool:
    return row.get('status') in ACTIVE_TASK_STATUSES


def is_task_terminal(row: dict) -> bool:
    return row.get('status') in store.terminal_for(str(row.get('flow') or 'run'))


def is_task_success(row: dict) -> bool:
    return row.get('status') in SUCCESS_TASK_STATUSES


def _pending_checkpoint(thread_dir: Path) -> dict | None:
    data = read_json(thread_dir / 'checkpoint.json')
    return data if data and data.get('status') == 'pending' else None


def _is_terminal_checkpoint(checkpoint: dict | None) -> bool:
    return bool(checkpoint and (
        checkpoint.get('terminal')
        or (checkpoint.get('completed_flow') == 'abtest' and not checkpoint.get('next_op'))
        or (checkpoint.get('stage') == 'abtest' and not checkpoint.get('next_op'))
    ))


def _public_flow_status(record: ThreadRecord) -> str:
    return {
        THREAD_WAITING: 'waiting_checkpoint',
        THREAD_SUCCEEDED: 'ended',
    }.get(record.state, record.state)


def _flow(row: dict | None) -> str | None:
    return row.get('flow') if row else None


def _error(row: dict | None) -> dict | None:
    if not row:
        return None
    if not row.get('error_code') and not row.get('error_kind'):
        return None
    return {'code': row.get('error_code'), 'kind': row.get('error_kind')}
