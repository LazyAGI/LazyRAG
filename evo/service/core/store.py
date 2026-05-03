from __future__ import annotations
import fcntl
import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from evo.runtime.fs import atomic_write as _atomic_write
from evo.service.core.errors import StateError

_LIFECYCLE: dict[str, dict[str, str]] = {
    'queued': {'start': 'running', 'cancel': 'cancelled'},
    'running': {
        'stop': 'stopping',
        'cancel': 'cancelled',
        'finish': 'succeeded',
        'fail_transient': 'failed_transient',
        'fail_permanent': 'failed_permanent',
    },
    'stopping': {'ack': 'paused', 'cancel': 'cancelled'},
    'paused': {'continue': 'running', 'cancel': 'cancelled'},
    'failed_transient': {'continue': 'running', 'cancel': 'cancelled'},
    'failed_permanent': {},
}
_APPLY_LIFECYCLE = {'succeeded': {'accept': 'accepted', 'reject': 'rejected'}, 'accepted': {}, 'rejected': {}}


def _merge_lifecycle(*parts: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    merged = {k: dict(v) for (k, v) in _LIFECYCLE.items()}
    for part in parts:
        for status, actions in part.items():
            merged.setdefault(status, {}).update(actions)
    return merged


_LEGAL: dict[str, dict[str, dict[str, str]]] = {
    'run': _merge_lifecycle(),
    'apply': _merge_lifecycle(_APPLY_LIFECYCLE),
    'eval': _merge_lifecycle(),
    'abtest': _merge_lifecycle(),
    'dataset_gen': _merge_lifecycle(),
}
TERMINAL: dict[str, set[str]] = {
    'dataset_gen': {'succeeded', 'failed_permanent', 'cancelled'},
    'eval': {'succeeded', 'failed_permanent', 'cancelled'},
    'run': {'succeeded', 'failed_permanent', 'cancelled'},
    'apply': {'succeeded', 'accepted', 'rejected', 'failed_permanent', 'cancelled'},
    'abtest': {'succeeded', 'failed_permanent', 'cancelled'},
}
FLOWS: tuple[str, ...] = ('dataset_gen', 'eval', 'run', 'apply', 'abtest')
_PATCH_FIELDS = frozenset(
    {
        'parent_run_id',
        'report_id',
        'base_commit',
        'branch_name',
        'final_commit',
        'current_step',
        'current_round',
        'error_code',
        'error_kind',
        'thread_id',
        'payload',
        'dataset_id',
        'source_eval_id',
    }
)
_ROUND_PATCH_FIELDS = frozenset({'phase', 'commit_sha', 'files_changed', 'test_passed', 'error_json', 'finished_at'})


def terminal_for(flow: str) -> tuple[str, ...]:
    return tuple(TERMINAL.get(flow, TERMINAL['run']))


def next_status(flow: str, status: str, action: str) -> str:
    nexts = _LEGAL.get(flow, {}).get(status, {})
    if action not in nexts:
        raise StateError(
            'ILLEGAL_TRANSITION', f'flow={flow} status={status} cannot {action}', {'allowed': sorted(nexts)}
        )
    return nexts[action]


def _new_id(flow: str) -> str:
    return f'{flow}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'


@contextmanager
def _flock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(path, 'a+b')
    try:
        fcntl.flock(fp, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fp, fcntl.LOCK_UN)
        finally:
            fp.close()


class FsStateStore:
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.tasks_dir = self.base_dir / 'tasks'
        self.rounds_dir = self.base_dir / 'apply_rounds'
        self._create_lock = self.base_dir / '_create.lock'
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        return None

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f'{task_id}.json'

    def round_path(self, apply_id: str, round_idx: int) -> Path:
        d = self.rounds_dir / apply_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f'{round_idx:06d}.json'

    def _all_task_files(self) -> list[Path]:
        return sorted(self.tasks_dir.glob('*.json'))


def open_db(path: Path | str) -> FsStateStore:
    p = Path(path)
    return FsStateStore(p.parent / 'state' if p.suffix else p)


def has_active(store: FsStateStore, flow: str, *, scope: str = 'global', thread_id: str | None = None) -> str | None:
    if scope not in ('global', 'thread'):
        raise ValueError("scope must be 'global' or 'thread'")
    terminals = set(terminal_for(flow))
    for path in store._all_task_files():
        rec = _read_task(path)
        if rec is None or rec.get('flow') != flow:
            continue
        if rec.get('status') in terminals:
            continue
        if scope == 'thread':
            if thread_id is None:
                raise ValueError('thread_id required when scope=thread')
            if rec.get('thread_id') != thread_id:
                continue
        return rec['id']
    return None


def list_active(store: FsStateStore, flow: str, *, scope: str = 'global', thread_id: str | None = None) -> list[dict]:
    if scope not in ('global', 'thread'):
        raise ValueError("scope must be 'global' or 'thread'")
    terminals = set(terminal_for(flow))
    out: list[dict] = []
    for path in store._all_task_files():
        rec = _read_task(path)
        if rec is None or rec.get('flow') != flow:
            continue
        if rec.get('status') in terminals:
            continue
        if scope == 'thread':
            if thread_id is None:
                raise ValueError('thread_id required when scope=thread')
            if rec.get('thread_id') != thread_id:
                continue
        out.append(rec)
    return out


def transition_many(store: FsStateStore, ids: list[str], action: str, **fields: Any) -> list[dict]:
    results: list[dict] = []
    with _flock(store._create_lock):
        for tid in ids:
            try:
                results.append(transition(store, tid, action, **fields))
            except StateError as exc:
                results.append({'id': tid, 'error': exc.to_payload()})
    return results


def create_task(
    store: FsStateStore,
    flow: str,
    *,
    parent_run_id: str | None = None,
    report_id: str | None = None,
    thread_id: str | None = None,
    payload: dict | None = None,
) -> str:
    if flow not in FLOWS:
        raise StateError('INVALID_FLOW', f'unknown flow {flow}')
    with _flock(store._create_lock):
        active = has_active(store, flow, scope='thread' if thread_id else 'global', thread_id=thread_id)
        if active:
            raise StateError(
                'ACTIVE_TASK_EXISTS', f'{flow} task {active} is not terminal', {'active_id': active, 'flow': flow}
            )
        tid = _new_id(flow)
        now = time.time()
        rec = {
            'id': tid,
            'flow': flow,
            'status': 'queued',
            'thread_id': thread_id,
            'parent_run_id': parent_run_id,
            'report_id': report_id,
            'base_commit': None,
            'branch_name': None,
            'final_commit': None,
            'current_step': None,
            'current_round': None,
            'request_stop': 0,
            'request_cancel': 0,
            'error_code': None,
            'error_kind': None,
            'payload': dict(payload or {}),
            'created_at': now,
            'updated_at': now,
            'terminal_at': None,
        }
        _write_task(store, rec)
        return tid


def get(store: FsStateStore, task_id: str) -> dict | None:
    return _read_task(store.task_path(task_id))


def must_get(store: FsStateStore, task_id: str) -> dict:
    rec = get(store, task_id)
    if rec is None:
        raise StateError('TASK_NOT_FOUND', f'task {task_id} not found')
    return rec


def transition(store: FsStateStore, task_id: str, action: str, **fields: Any) -> dict:
    path = store.task_path(task_id)
    with _flock(path):
        rec = _read_task(path)
        if rec is None:
            raise StateError('TASK_NOT_FOUND', f'task {task_id} not found')
        new_status = next_status(rec['flow'], rec['status'], action)
        now = time.time()
        rec['status'] = new_status
        rec['updated_at'] = now
        if new_status in terminal_for(rec['flow']):
            rec['terminal_at'] = now
        if action == 'stop':
            rec['request_stop'] = 1
        elif action == 'cancel':
            rec['request_cancel'] = 1
        elif action == 'ack':
            rec['request_stop'] = 0
        for k, v in fields.items():
            if k not in _PATCH_FIELDS:
                raise ValueError(f'unsupported field {k}')
            rec[k] = v
        _write_task(store, rec)
        return rec


def patch(store: FsStateStore, task_id: str, **fields: Any) -> None:
    if not fields:
        return
    path = store.task_path(task_id)
    with _flock(path):
        rec = _read_task(path)
        if rec is None:
            raise StateError('TASK_NOT_FOUND', f'task {task_id} not found')
        rec['updated_at'] = time.time()
        for k, v in fields.items():
            if k not in _PATCH_FIELDS:
                raise ValueError(f'unsupported field {k}')
            rec[k] = v
        _write_task(store, rec)


def signals(store: FsStateStore, task_id: str) -> dict:
    rec = must_get(store, task_id)
    return {'stop': bool(rec.get('request_stop')), 'cancel': bool(rec.get('request_cancel'))}


def list_recent(store: FsStateStore, flow: str, limit: int = 50) -> list[dict]:
    out = [rec for path in store._all_task_files() if (rec := _read_task(path)) and rec.get('flow') == flow]
    out.sort(key=lambda r: r.get('created_at', 0), reverse=True)
    return out[:limit]


def latest_succeeded_run(store: FsStateStore) -> dict | None:
    best: dict | None = None
    best_t = -1.0
    for path in store._all_task_files():
        rec = _read_task(path)
        if rec and rec.get('flow') == 'run' and (rec.get('status') == 'succeeded'):
            ts = rec.get('terminal_at') or 0.0
            if ts > best_t:
                best, best_t = (rec, ts)
    return best


def append_round(store: FsStateStore, apply_id: str, round_idx: int, *, phase: str = 'init') -> None:
    rec = {
        'apply_id': apply_id,
        'round': round_idx,
        'phase': phase,
        'commit_sha': None,
        'files_changed': None,
        'test_passed': None,
        'error_json': None,
        'started_at': time.time(),
        'finished_at': None,
    }
    _atomic_write(store.round_path(apply_id, round_idx), json.dumps(rec, ensure_ascii=False, indent=2))


def update_round(store: FsStateStore, apply_id: str, round_idx: int, **fields: Any) -> None:
    if not fields:
        return
    path = store.round_path(apply_id, round_idx)
    with _flock(path):
        rec = _read_task(path)
        if rec is None:
            raise StateError('ROUND_NOT_FOUND', f'apply {apply_id} round {round_idx} not found')
        for k, v in fields.items():
            if k not in _ROUND_PATCH_FIELDS:
                raise ValueError(f'unsupported round field {k}')
            if k == 'files_changed' and (not isinstance(v, str)):
                v = json.dumps(list(v), ensure_ascii=False)
            if k == 'error_json' and isinstance(v, dict):
                v = json.dumps(v, ensure_ascii=False)
            rec[k] = v
        _atomic_write(path, json.dumps(rec, ensure_ascii=False, indent=2))


def list_rounds(store: FsStateStore, apply_id: str) -> list[dict]:
    d = store.rounds_dir / apply_id
    if not d.exists():
        return []
    return [rec for path in sorted(d.glob('*.json')) if (rec := _read_task(path)) is not None]


def list_flow_tasks_by_thread(store: FsStateStore, flow: str, thread_id: str) -> list[dict]:
    out: list[dict] = []
    for path in store._all_task_files():
        rec = _read_task(path)
        if rec and rec.get('flow') == flow and (rec.get('thread_id') == thread_id):
            out.append(rec)
    out.sort(key=lambda r: r.get('created_at', 0.0))
    return out


def _read_task(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _write_task(store: FsStateStore, rec: dict) -> None:
    text = json.dumps(rec, ensure_ascii=False, indent=2)
    _atomic_write(store.task_path(rec['id']), text)
    if rec.get('thread_id'):
        _atomic_write(store.base_dir / 'threads' / rec['thread_id'] / 'tasks' / f"{rec['id']}.json", text)
