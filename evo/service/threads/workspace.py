from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from evo.runtime.fs import atomic_write as _atomic_write_text

TERMINAL_STATUSES = frozenset({
    'succeeded', 'failed_transient', 'failed_permanent',
    'cancelled', 'accepted', 'rejected',
})

ARTIFACT_KINDS: tuple[str, ...] = (
    'run_ids', 'apply_ids', 'eval_ids', 'abtest_ids', 'chat_ids',
    'dataset_ids', 'apply_commit_ids',
)

_SUBDIRS: tuple[str, ...] = ('tasks',)

_SECRET_KEYS = ('api_key', 'apikey', 'token', 'password', 'authorization',
                'secret', 'access_key')
_MAX_INLINE_CHARS = int(os.getenv('EVO_EVENT_MAX_INLINE_CHARS', '60000'))

EVENT_TAGS: frozenset[str] = frozenset({
    'dataset_gen.start', 'dataset_gen.progress', 'dataset_gen.finish', 'dataset_gen.cancel',
    'eval.start', 'eval.progress', 'eval.finish', 'eval.cancel',
    'run.start', 'run.finish', 'run.cancel', 'run.pause', 'run.resume',
    'run.indexer.result', 'run.conductor.result', 'run.researcher.result', 'run.tool.used',
    'apply.start', 'apply.finish', 'apply.cancel', 'apply.pause', 'apply.resume',
    'apply.round.diff',
    'abtest.start', 'abtest.progress', 'abtest.finish',
    'message.user', 'message.assistant',
    'intent.thought', 'intent.reply',
})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _legacy_tag(actor: str, kind: str) -> str | None:
    if kind in EVENT_TAGS:
        return kind
    mapping = {
        'user.message': 'message.user',
        'assistant.reply': 'message.assistant',
        'assistant.thinking': 'intent.thought',
        'dataset_gen.complete': 'dataset_gen.finish',
        'eval.run.start': 'eval.start',
        'eval.fetch.start': 'eval.start',
        'eval.ready': 'eval.finish',
        'eval.complete': 'eval.finish',
        'apply.complete': 'apply.finish',
        'apply.round': 'apply.round.diff',
    }
    tag = mapping.get(kind)
    if tag in EVENT_TAGS:
        return tag
    if actor == 'user' and kind.endswith('message'):
        return 'message.user'
    return None


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
    def __init__(self, base_dir: Path | str, thread_id: str,
                 *, create: bool = True) -> None:
        self.thread_id = thread_id
        self.dir = Path(base_dir) / 'state' / 'threads' / thread_id
        if create:
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

    @property
    def outputs_dir(self) -> Path:
        d = self.dir / 'outputs'
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
                obj = json.loads(line.decode('utf-8', 'replace'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if 'seq' in obj:
                return int(obj['seq'])
        return 0

    def append_event(self, tag: str, *, thread_id: str | None = None,
                     task_id: str | None = None,
                     payload: dict | None = None,
                     src_ts: str | None = None) -> int:
        if tag not in EVENT_TAGS:
            return 0
        stage, event = tag.split('.', 1)
        ev: dict[str, Any] = {
            'seq': 0, 'ts': _utc_now_iso(),
            'thread_id': thread_id or self._path.parent.name,
            'tag': tag,
            'stage': stage,
            'event': event,
            'task_id': task_id,
            'payload': _redact(payload or {}),
        }
        if src_ts:
            ev['src_ts'] = src_ts
        return self._append_record(ev)

    def append(self, actor: str, kind: str,
               payload: dict | None = None,
               *, src_ts: str | None = None) -> int:
        tag = _legacy_tag(actor, kind)
        if tag is None:
            return 0
        task_id = None
        if isinstance(payload, dict):
            task_id = payload.get('task_id')
        return self.append_event(tag, task_id=task_id, payload=payload,
                                 src_ts=src_ts)

    def _append_record(self, ev: dict[str, Any]) -> int:
        with self._lock:
            line = (json.dumps(ev, ensure_ascii=False, default=str) + '\n').encode('utf-8')
            with open(self._path, 'ab') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    self._seq = max(self._seq, self._recover_seq()) + 1
                    ev['seq'] = self._seq
                    line = (json.dumps(ev, ensure_ascii=False, default=str) + '\n').encode('utf-8')
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        return ev['seq']


class EventSink:
    def __init__(self, ws: ThreadWorkspace) -> None:
        self.ws = ws
        self.log = EventLog(ws.events_path)
        self.payload_dir = ws.dir / 'event_payloads'

    def emit(self, kind: str, *, actor: str, level: str = 'info',
             task_id: str | None = None, op_id: str | None = None,
             input: Any = None, output: Any = None, error: Any = None,
             artifacts: list[dict] | dict | None = None,
             duration_ms: float | None = None,
             metadata: dict | None = None) -> int:
        tag = _legacy_tag(actor, kind)
        if tag is None:
            return 0
        payload: dict[str, Any] = {}
        if task_id:
            payload['task_id'] = task_id
        if op_id:
            payload['op_id'] = op_id
        if input is not None:
            payload['input'] = self._prepare(input, kind, 'input')
        if output is not None:
            payload['output'] = self._prepare(output, kind, 'output')
        if error is not None:
            payload['error'] = self._prepare(error, kind, 'error')
        if artifacts is not None:
            payload['artifacts'] = self._prepare(artifacts, kind, 'artifacts')
        if duration_ms is not None:
            payload['duration_ms'] = round(float(duration_ms), 3)
        if metadata:
            payload['metadata'] = self._prepare(metadata, kind, 'metadata')
        return self.log.append_event(tag, task_id=task_id, payload=payload)

    def _prepare(self, value: Any, kind: str, slot: str) -> Any:
        return self._spill_large(_redact(value), kind, slot)

    def _spill_large(self, value: Any, kind: str, slot: str) -> Any:
        if isinstance(value, str) and len(value) > _MAX_INLINE_CHARS:
            return self._write_payload(value, kind, slot, 'txt')
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, default=str)
            if len(text) > _MAX_INLINE_CHARS:
                return self._write_payload(text, kind, slot, 'json')
        return value

    def _write_payload(self, text: str, kind: str, slot: str, suffix: str) -> dict:
        raw = text.encode('utf-8')
        digest = hashlib.sha256(raw).hexdigest()
        safe_kind = ''.join(ch if ch.isalnum() or ch in '._-' else '_'
                            for ch in kind)[:80]
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        path = self.payload_dir / f'{int(time.time() * 1000)}_{safe_kind}_{slot}_{digest[:12]}.{suffix}'
        path.write_bytes(raw)
        return {
            'artifact_path': str(path),
            'sha256': digest,
            'bytes': len(raw),
            'preview': text[:1000],
        }


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if any(secret in str(k).lower() for secret in _SECRET_KEYS):
                out[k] = _mask_secret(v)
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact(v) for v in value)
    return value


def _mask_secret(value: Any) -> str:
    text = str(value)
    if not text:
        return ''
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]
    return f'<redacted sha256:{digest}>'


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
