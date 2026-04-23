from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

RUN_TERMINAL = ('succeeded', 'cancelled')
APPLY_TERMINAL = ('accepted', 'rejected', 'cancelled')

_LEGAL: dict[str, dict[str, dict[str, str]]] = {
    'run': {
        'queued':           {'cancel': 'cancelled'},
        'running':          {'stop': 'stopping', 'cancel': 'cancelled',
                             'finish': 'succeeded',
                             'fail_transient': 'failed_transient',
                             'fail_permanent': 'failed_permanent'},
        'stopping':         {'ack': 'paused', 'cancel': 'cancelled'},
        'paused':           {'continue': 'running', 'cancel': 'cancelled'},
        'failed_transient': {'continue': 'running', 'cancel': 'cancelled'},
        'failed_permanent': {'cancel': 'cancelled'},
    },
    'apply': {
        'queued':           {'cancel': 'cancelled'},
        'running':          {'stop': 'stopping', 'cancel': 'cancelled',
                             'finish': 'succeeded',
                             'fail_transient': 'failed_transient',
                             'fail_permanent': 'failed_permanent'},
        'stopping':         {'ack': 'paused', 'cancel': 'cancelled'},
        'paused':           {'continue': 'running', 'cancel': 'cancelled'},
        'failed_transient': {'continue': 'running', 'cancel': 'cancelled'},
        'failed_permanent': {'cancel': 'cancelled'},
        'succeeded':        {'accept': 'accepted', 'reject': 'rejected'},
    },
}

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  flow TEXT NOT NULL CHECK(flow IN ('run','apply')),
  status TEXT NOT NULL,
  parent_run_id TEXT,
  report_id TEXT,
  base_commit TEXT,
  branch_name TEXT,
  current_step TEXT,
  current_round INTEGER,
  request_stop INTEGER NOT NULL DEFAULT 0,
  request_cancel INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_kind TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  terminal_at REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_flow_status ON tasks(flow, status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);

CREATE TABLE IF NOT EXISTS apply_rounds (
  apply_id TEXT NOT NULL,
  round INTEGER NOT NULL,
  phase TEXT,
  commit_sha TEXT,
  files_changed TEXT,
  test_passed INTEGER,
  error_json TEXT,
  started_at REAL,
  finished_at REAL,
  PRIMARY KEY (apply_id, round)
);
'''


class StateError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(f'[{code}] {message}')
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_payload(self) -> dict:
        return {'code': self.code, 'message': self.message, 'details': dict(self.details)}


def terminal_for(flow: str) -> tuple[str, ...]:
    return RUN_TERMINAL if flow == 'run' else APPLY_TERMINAL


def next_status(flow: str, status: str, action: str) -> str:
    nexts = _LEGAL.get(flow, {}).get(status, {})
    if action not in nexts:
        raise StateError('ILLEGAL_TRANSITION',
                         f'flow={flow} status={status} cannot {action}',
                         {'allowed': sorted(nexts)})
    return nexts[action]


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(_SCHEMA)
    return conn


def _new_id(flow: str) -> str:
    return f'{flow}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'


def has_active(conn: sqlite3.Connection, flow: str) -> str | None:
    terminals = terminal_for(flow)
    placeholders = ','.join('?' * len(terminals))
    cur = conn.execute(
        f'SELECT id FROM tasks WHERE flow=? AND status NOT IN ({placeholders}) LIMIT 1',
        (flow, *terminals),
    )
    row = cur.fetchone()
    return row['id'] if row else None


def create_task(conn: sqlite3.Connection, flow: str, *,
                parent_run_id: str | None = None,
                report_id: str | None = None) -> str:
    if flow not in ('run', 'apply'):
        raise StateError('INVALID_FLOW', f'unknown flow {flow}')
    conn.execute('BEGIN IMMEDIATE')
    try:
        active = has_active(conn, flow)
        if active:
            raise StateError('ACTIVE_TASK_EXISTS',
                             f'{flow} task {active} is not terminal',
                             {'active_id': active, 'flow': flow})
        tid = _new_id(flow)
        now = time.time()
        conn.execute(
            'INSERT INTO tasks (id, flow, status, parent_run_id, report_id, '
            'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (tid, flow, 'queued', parent_run_id, report_id, now, now),
        )
        conn.execute('COMMIT')
        return tid
    except Exception:
        conn.execute('ROLLBACK')
        raise


def get(conn: sqlite3.Connection, task_id: str) -> dict | None:
    cur = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def must_get(conn: sqlite3.Connection, task_id: str) -> dict:
    row = get(conn, task_id)
    if row is None:
        raise StateError('TASK_NOT_FOUND', f'task {task_id} not found')
    return row


def transition(conn: sqlite3.Connection, task_id: str, action: str,
               **fields: Any) -> dict:
    row = must_get(conn, task_id)
    flow = row['flow']
    new_status = next_status(flow, row['status'], action)
    now = time.time()
    sets = ['status=?', 'updated_at=?']
    vals: list[Any] = [new_status, now]
    if new_status in terminal_for(flow):
        sets.append('terminal_at=?')
        vals.append(now)
    if action in ('stop',):
        sets.append('request_stop=1')
    if action in ('cancel',):
        sets.append('request_cancel=1')
    if action == 'ack':
        sets.append('request_stop=0')
    for k, v in fields.items():
        if k not in {'parent_run_id', 'report_id', 'base_commit', 'branch_name',
                     'current_step', 'current_round', 'error_code', 'error_kind'}:
            raise ValueError(f'unsupported field {k}')
        sets.append(f'{k}=?')
        vals.append(v)
    vals.append(task_id)
    conn.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)
    return must_get(conn, task_id)


def patch(conn: sqlite3.Connection, task_id: str, **fields: Any) -> None:
    if not fields:
        return
    sets = ['updated_at=?']
    vals: list[Any] = [time.time()]
    for k, v in fields.items():
        sets.append(f'{k}=?')
        vals.append(v)
    vals.append(task_id)
    conn.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)


def signals(conn: sqlite3.Connection, task_id: str) -> dict:
    row = must_get(conn, task_id)
    return {'stop': bool(row['request_stop']), 'cancel': bool(row['request_cancel'])}


def list_recent(conn: sqlite3.Connection, flow: str, limit: int = 50) -> list[dict]:
    cur = conn.execute(
        'SELECT * FROM tasks WHERE flow=? ORDER BY created_at DESC LIMIT ?',
        (flow, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def latest_succeeded_run(conn: sqlite3.Connection) -> dict | None:
    cur = conn.execute(
        "SELECT * FROM tasks WHERE flow='run' AND status='succeeded' "
        "ORDER BY terminal_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    return dict(row) if row else None


def append_round(conn: sqlite3.Connection, apply_id: str, round_idx: int,
                 *, phase: str = 'init') -> None:
    conn.execute(
        'INSERT OR REPLACE INTO apply_rounds (apply_id, round, phase, started_at) '
        'VALUES (?, ?, ?, ?)',
        (apply_id, round_idx, phase, time.time()),
    )


def update_round(conn: sqlite3.Connection, apply_id: str, round_idx: int,
                 **fields: Any) -> None:
    if not fields:
        return
    sets: list[str] = []
    vals: list[Any] = []
    for k, v in fields.items():
        if k not in {'phase', 'commit_sha', 'files_changed', 'test_passed',
                     'error_json', 'finished_at'}:
            raise ValueError(f'unsupported round field {k}')
        if k == 'files_changed' and not isinstance(v, str):
            v = json.dumps(list(v), ensure_ascii=False)
        if k == 'error_json' and isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f'{k}=?')
        vals.append(v)
    vals.extend([apply_id, round_idx])
    conn.execute(
        f'UPDATE apply_rounds SET {", ".join(sets)} WHERE apply_id=? AND round=?',
        vals,
    )


def list_rounds(conn: sqlite3.Connection, apply_id: str) -> list[dict]:
    cur = conn.execute(
        'SELECT * FROM apply_rounds WHERE apply_id=? ORDER BY round',
        (apply_id,),
    )
    return [dict(r) for r in cur.fetchall()]
