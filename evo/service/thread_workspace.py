from __future__ import annotations

import asyncio
import fcntl
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

TERMINAL_STATUSES = frozenset({
    'succeeded', 'failed_transient', 'failed_permanent',
    'cancelled', 'accepted', 'rejected',
})

ARTIFACT_KINDS: tuple[str, ...] = (
    'run_ids', 'apply_ids', 'eval_ids', 'abtest_ids', 'chat_ids',
)

_SUBDIRS: tuple[str, ...] = (
    'tasks', 'checkpoints', 'evals', 'traces',
    'runs', 'applies', 'abtests',
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


from evo.runtime.fs import atomic_write as _atomic_write_text  # noqa: E402


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(path.parent / (path.name + '.lock'), 'a+b')
    try:
        fcntl.flock(fp, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fp, fcntl.LOCK_UN)
        finally:
            fp.close()


class ThreadWorkspace:
    def __init__(self, base_dir: Path | str, thread_id: str) -> None:
        self.thread_id = thread_id
        self.dir = Path(base_dir) / 'state' / 'threads' / thread_id
        self.dir.mkdir(parents=True, exist_ok=True)
        for sub in _SUBDIRS:
            (self.dir / sub).mkdir(exist_ok=True)

    @property
    def thread_meta_path(self) -> Path: return self.dir / 'thread.json'
    @property
    def events_path(self) -> Path: return self.dir / 'events.jsonl'
    @property
    def messages_path(self) -> Path: return self.dir / 'messages.jsonl'
    @property
    def artifacts_path(self) -> Path: return self.dir / 'artifacts.json'

    def task_path(self, task_id: str) -> Path:
        return self.dir / 'tasks' / f'{task_id}.json'

    def task_cursor(self, task_id: str) -> Path:
        return self.dir / 'tasks' / f'{task_id}.cursor'

    def checkpoint_path(self, cp_id: str) -> Path:
        return self.dir / 'checkpoints' / f'{cp_id}.json'

    def eval_path(self, eval_id: str) -> Path:
        return self.dir / 'evals' / f'{eval_id}.json'

    def trace_path(self, trace_id: str) -> Path:
        return self.dir / 'traces' / f'{trace_id}.json'

    def trace_bundle_path(self, eval_id: str) -> Path:
        return self.dir / 'traces' / f'{eval_id}.bundle.json'

    def run_dir(self, run_id: str) -> Path:
        d = self.dir / 'runs' / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def apply_dir(self, apply_id: str) -> Path:
        d = self.dir / 'applies' / apply_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def abtest_dir(self, abtest_id: str) -> Path:
        d = self.dir / 'abtests' / abtest_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def load_artifacts(self) -> dict[str, list[str]]:
        data = _read_json(self.artifacts_path) or {}
        for k in ARTIFACT_KINDS:
            data.setdefault(k, [])
        return data

    def attach_artifact(self, kind: str, value: str) -> None:
        if kind not in ARTIFACT_KINDS:
            raise ValueError(f'unknown artifact kind {kind!r}')
        with _file_lock(self.artifacts_path):
            data = self.load_artifacts()
            if value not in data[kind]:
                data[kind].append(value)
                _atomic_write_text(self.artifacts_path,
                                    json.dumps(data, ensure_ascii=False, indent=2))


class EventLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._seq = self._recover_seq()

    def _recover_seq(self) -> int:
        if not self._path.exists() or self._path.stat().st_size == 0:
            return 0
        with open(self._path, 'rb') as f:
            try:
                f.seek(-8192, os.SEEK_END)
            except OSError:
                f.seek(0)
            tail = f.read()
        for raw in reversed(tail.splitlines()):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if 'seq' in obj:
                return int(obj['seq'])
        return 0

    def append(self, actor: str, kind: str,
               payload: dict | None = None,
               *, src_ts: str | None = None) -> int:
        ev: dict[str, Any] = {
            'seq': 0, 'ts': _utc_now_iso(),
            'actor': actor, 'kind': kind, 'payload': payload or {},
        }
        if src_ts:
            ev['src_ts'] = src_ts
        with self._lock:
            self._seq += 1
            ev['seq'] = self._seq
            line = (json.dumps(ev, ensure_ascii=False, default=str) + '\n').encode('utf-8')
            with open(self._path, 'ab') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        return ev['seq']


StatusGetter = Callable[[], 'str | None']


class Tailer:
    def __init__(self, *, task_id: str, actor: str,
                 src_path: Path, cursor_path: Path,
                 log: EventLog, get_status: StatusGetter,
                 poll_s: float = 0.2,
                 max_line_bytes: int = 1 << 20) -> None:
        self.task_id = task_id
        self.actor = actor
        self.src = src_path
        self.cursor = cursor_path
        self.log = log
        self.get_status = get_status
        self.poll = poll_s
        self.max_line = max_line_bytes
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.get_event_loop().create_task(
            self._run(), name=f'tailer:{self.task_id}')

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        offset = self._load_cursor()
        try:
            while True:
                size = self.src.stat().st_size if self.src.exists() else 0
                if size < offset:
                    self.log.append(self.actor, 'tailer.reset',
                                    {'old_offset': offset, 'new_size': size})
                    offset = 0
                    self._save_cursor(0)
                if size > offset:
                    offset = self._consume(offset, size)
                drained = offset == size
                if drained and (self.get_status() in TERMINAL_STATUSES
                                 or self._stop.is_set()):
                    break
                await asyncio.sleep(self.poll)
        finally:
            self.log.append(self.actor, 'tailer.stopped', {'final_offset': offset})

    def _consume(self, offset: int, size: int) -> int:
        with open(self.src, 'rb') as f:
            f.seek(offset)
            chunk = f.read(size - offset)
        consumed = 0
        while True:
            nl = chunk.find(b'\n', consumed)
            if nl < 0:
                tail_len = len(chunk) - consumed
                if tail_len > self.max_line:
                    self.log.append(self.actor, 'tailer.giant_line',
                                    {'bytes': tail_len})
                    consumed = len(chunk)
                break
            self._emit(chunk[consumed:nl])
            consumed = nl + 1
        new_offset = offset + consumed
        if new_offset != offset:
            self._save_cursor(new_offset)
        return new_offset

    def _emit(self, raw: bytes) -> None:
        text = raw.strip()
        if not text:
            return
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            self.log.append(self.actor, 'tailer.parse_error',
                            {'raw': text[:512].decode('utf-8', 'replace'),
                             'error': str(exc)})
            return
        if not isinstance(obj, dict):
            return
        kind = str(obj.pop('type', 'telemetry'))
        ts_src = obj.pop('ts', None)
        self.log.append(self.actor, kind, obj, src_ts=ts_src)

    def _load_cursor(self) -> int:
        try:
            return int(self.cursor.read_text(encoding='utf-8').strip() or '0')
        except (FileNotFoundError, ValueError):
            return 0

    def _save_cursor(self, offset: int) -> None:
        _atomic_write_text(self.cursor, str(offset))


_RESOLVE_MAP = {'approve': 'approved', 'cancel': 'cancelled', 'revise': 'revised'}


class CheckpointStore:
    def __init__(self, ws: ThreadWorkspace, log: EventLog) -> None:
        self._ws = ws
        self._log = log

    def create(self, *, task_id: str, kind: str, title: str,
               payload: dict, options: list[str] | None = None,
               default: str | None = None) -> str:
        cp_id = f'cp-{uuid.uuid4().hex[:8]}'
        rec = {
            'id': cp_id, 'thread_id': self._ws.thread_id,
            'task_id': task_id, 'kind': kind, 'title': title,
            'payload': payload,
            'options': options or ['approve', 'cancel', 'revise'],
            'default': default,
            'status': 'pending', 'response': None,
            'created_at': time.time(),
            'responded_at': None, 'responder': None,
        }
        _atomic_write_text(self._ws.checkpoint_path(cp_id),
                            json.dumps(rec, ensure_ascii=False, indent=2))
        self._log.append(f'task:{task_id}', 'checkpoint.required',
                         {'cp_id': cp_id, 'kind': kind, 'title': title})
        return cp_id

    def get(self, cp_id: str) -> dict | None:
        return _read_json(self._ws.checkpoint_path(cp_id))

    def list_pending(self) -> list[dict]:
        out = []
        for path in sorted((self._ws.dir / 'checkpoints').glob('*.json')):
            rec = _read_json(path)
            if rec and rec.get('status') == 'pending':
                out.append(rec)
        return out

    def respond(self, cp_id: str, *, choice: str,
                feedback: str | None = None,
                responder: str = 'user') -> dict:
        path = self._ws.checkpoint_path(cp_id)
        rec = _read_json(path)
        if rec is None:
            raise KeyError(cp_id)
        if rec['status'] != 'pending':
            raise RuntimeError(f'checkpoint {cp_id} already {rec["status"]}')
        rec.update({
            'status': _RESOLVE_MAP.get(choice, choice),
            'response': {'choice': choice, 'feedback': feedback},
            'responded_at': time.time(),
            'responder': responder,
        })
        _atomic_write_text(path, json.dumps(rec, ensure_ascii=False, indent=2))
        self._log.append(f'task:{rec["task_id"]}', 'checkpoint.resolved',
                         {'cp_id': cp_id, 'choice': choice, 'responder': responder})
        return rec

    def wait(self, cp_id: str, *,
             cancel_token: Callable[[], bool] | None = None,
             poll_s: float = 0.2,
             timeout_s: float | None = None) -> dict:
        deadline = time.time() + timeout_s if timeout_s else None
        while True:
            rec = self.get(cp_id)
            if rec is None:
                raise KeyError(cp_id)
            if rec['status'] != 'pending':
                return rec
            if cancel_token and cancel_token():
                raise RuntimeError(f'wait cancelled while waiting for {cp_id}')
            if deadline and time.time() > deadline:
                raise TimeoutError(cp_id)
            time.sleep(poll_s)


class ThreadLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = threading.Lock()

    def get(self, thread_id: str) -> asyncio.Lock:
        with self._guard:
            lock = self._locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[thread_id] = lock
            return lock
