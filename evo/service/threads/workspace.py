from __future__ import annotations
import fcntl
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from evo.runtime.fs import atomic_write as _atomic_write
from evo.runtime.config import EVO_EVENT_MAX_INLINE_CHARS
ARTIFACT_KINDS = ('run_ids', 'apply_ids', 'eval_ids', 'abtest_ids', 'chat_ids', 'dataset_ids', 'apply_commit_ids')
_MAX_INLINE_CHARS = EVO_EVENT_MAX_INLINE_CHARS
EVENT_TAGS = frozenset({
    'dataset_gen.start', 'dataset_gen.progress', 'dataset_gen.finish', 'dataset_gen.failed', 'dataset_gen.cancel',
    'eval.start', 'eval.progress', 'eval.finish', 'eval.failed', 'eval.cancel',
    'run.start', 'run.progress', 'run.finish', 'run.failed', 'run.cancel', 'run.pause', 'run.resume',
    'run.indexer.result', 'run.conductor.result', 'run.researcher.result', 'run.tool.used',
    'apply.start', 'apply.finish', 'apply.failed', 'apply.cancel', 'apply.pause', 'apply.resume',
    'apply.round.start', 'apply.round.finish', 'apply.round.diff',
    'abtest.start', 'abtest.progress', 'abtest.finish', 'abtest.failed',
    'message.user', 'message.assistant', 'intent.thought', 'intent.reply',
    'checkpoint.wait', 'checkpoint.continue', 'checkpoint.rewind', 'checkpoint.answer', 'checkpoint.cancel',
})


class ThreadWorkspace:
    def __init__(self, base_dir: Path | str, thread_id: str, *, create: bool = True) -> None:
        self.thread_id = thread_id
        self.dir = Path(base_dir) / 'state' / 'threads' / thread_id
        if create:
            self.dir.mkdir(parents=True, exist_ok=True)
    thread_meta_path = property(lambda s: s.dir / 'thread.json')
    events_path = property(lambda s: s.dir / 'events.jsonl')
    messages_path = property(lambda s: s.dir / 'messages.jsonl')
    artifacts_path = property(lambda s: s.dir / 'artifacts.json')
    checkpoint_path = property(lambda s: s.dir / 'checkpoint.json')
    outputs_dir = property(lambda s: _mkdir(s.dir / 'outputs'))

    def eval_path(self, eval_id: str) -> Path:
        return self.dir / 'evals' / f'{eval_id}.json'

    def trace_bundle_path(self, eval_id: str) -> Path:
        return self.dir / 'traces' / f'{eval_id}.bundle.json'

    def abtest_dir(self, abtest_id: str) -> Path:
        return _mkdir(self.dir / 'abtests' / abtest_id)

    def load_artifacts(self) -> dict[str, list[str]]:
        data = _read_json(self.artifacts_path) or {}
        for kind in ARTIFACT_KINDS:
            data.setdefault(kind, [])
        return data

    def attach_artifact(self, kind: str, value: str) -> None:
        if kind not in ARTIFACT_KINDS:
            raise ValueError(f'unknown artifact kind {kind!r}')
        with _file_lock(self.artifacts_path):
            data = self.load_artifacts()
            if value not in data[kind]:
                data[kind].append(value)
                _write_json(self.artifacts_path, data)

    def load_checkpoint(self) -> dict | None:
        data = _read_json(self.checkpoint_path)
        return data if data and data.get('status') == 'pending' else None

    def save_checkpoint(self, data: dict) -> dict:
        payload = {'status': 'pending', 'created_at': time.time(), **data}
        _write_json(self.checkpoint_path, payload)
        return payload

    def clear_checkpoint(self) -> None:
        _write_json(self.checkpoint_path, {'status': 'cleared', 'updated_at': time.time()})


class EventLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._seq = _last_event_seq(path)

    def append_event(
            self,
            tag: str,
            *,
            thread_id: str | None = None,
            task_id: str | None = None,
            payload: dict | None = None,
            src_ts: str | None = None) -> int:
        if tag not in EVENT_TAGS:
            return 0
        stage, event = tag.split('.', 1)
        row = {
            'seq': 0,
            'ts': _utc_now(),
            'thread_id': thread_id or self._path.parent.name,
            'tag': tag,
            'stage': stage,
            'event': event,
            'task_id': task_id,
            'payload': _redact(payload or {}),
        }
        if src_ts:
            row['src_ts'] = src_ts
        return self._append(row)

    def append(self, actor: str, kind: str, payload: dict | None = None, *, src_ts: str | None = None) -> int:
        return self.append_event(
            _legacy_tag(actor, kind) or '',
            task_id=(payload or {}).get('task_id'),
            payload=payload,
            src_ts=src_ts,
        )

    def _append(self, row: dict) -> int:
        with self._lock:
            with self._path.open('ab') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                self._seq = max(self._seq, _last_event_seq(self._path)) + 1
                row['seq'] = self._seq
                f.write((json.dumps(row, ensure_ascii=False, default=str) + '\n').encode())
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f, fcntl.LOCK_UN)
        return self._seq


class EventSink:
    def __init__(self, ws: ThreadWorkspace) -> None:
        self.ws = ws
        self.log = EventLog(ws.events_path)

    def emit(
            self,
            kind: str,
            *,
            actor: str,
            level: str = 'info',
            task_id: str | None = None,
            op_id: str | None = None,
            input: Any = None,
            output: Any = None,
            error: Any = None,
            artifacts: list[dict] | dict | None = None,
            duration_ms: float | None = None,
            metadata: dict | None = None) -> int:
        payload = {
            k: v for k,
            v in {
                'task_id': task_id,
                'op_id': op_id,
                'input': input,
                'output': output,
                'error': error,
                'artifacts': artifacts,
                'duration_ms': duration_ms,
                'metadata': metadata,
                'level': level,
            }.items()
            if v is not None
        }
        payload = _shape_runtime_payload(kind, actor, payload)
        return self.log.append(actor, kind, {k: self._prepare(v, kind, k) for k, v in payload.items()})

    def _prepare(self, value: Any, kind: str, slot: str) -> Any:
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= _MAX_INLINE_CHARS:
            return _redact(value)
        return {'truncated': text[:_MAX_INLINE_CHARS], 'bytes': len(text)}


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _last_event_seq(path: Path) -> int:
    try:
        with path.open('rb') as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            buf = b''
            while pos > 0 and b'\n' not in buf.rstrip(b'\n'):
                step = min(4096, pos)
                pos -= step
                f.seek(pos)
                buf = f.read(step) + buf
        for line in reversed(buf.splitlines()):
            if line.strip():
                return int((json.loads(line).get('seq') or 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0
    return 0


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, default=str))


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(path.parent / (path.name + '.lock'), 'a+b')
    try:
        fcntl.flock(fp, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fp, fcntl.LOCK_UN)
        fp.close()


def _legacy_tag(actor: str, kind: str) -> str | None:
    mapping = {
        'user.message': 'message.user',
        'assistant.reply': 'message.assistant',
        'assistant.thinking': 'intent.thought',
        'dataset_gen.complete': 'dataset_gen.finish',
        'eval.ready': 'eval.finish',
        'eval.complete': 'eval.finish',
        'stage.completed': 'run.progress',
        'conductor.stage_advanced': 'run.conductor.result',
        'researcher.reasoning_summary': 'run.researcher.result',
        'researcher.tool_call.completed': 'run.tool.used',
        'tool_call': 'run.tool.used',
        'apply.complete': 'apply.finish',
    }
    tag = kind if kind in EVENT_TAGS else mapping.get(kind)
    if tag in EVENT_TAGS:
        return tag
    return 'message.user' if actor == 'user' and kind.endswith('message') else None


def _shape_runtime_payload(kind: str, actor: str, payload: dict) -> dict:
    output = payload.get('output')
    metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
    shaped = dict(payload)
    if kind == 'researcher.tool_call.completed':
        if actor != 'researcher':
            shaped.setdefault('agent', actor)
        for key in ('round', 'tool', 'args', 'ok', 'handle', 'summary', 'elapsed_s'):
            if key in metadata:
                shaped.setdefault(key, metadata[key])
    elif kind == 'researcher.reasoning_summary':
        out = output if isinstance(output, dict) else {}
        summary = _parse_json_object(out.get('final_answer'))
        agent = actor
        if agent == 'researcher' and summary and summary.get('hypothesis_id'):
            agent = f"researcher:{summary['hypothesis_id']}"
        if agent != 'researcher':
            shaped.setdefault('agent', agent)
        for key in ('rounds', 'tool_calls', 'exhausted'):
            if key in out:
                shaped.setdefault(key, out[key])
        if 'final_answer' in out:
            shaped.setdefault('final_answer', out['final_answer'])
            if summary:
                shaped.setdefault('result_summary', summary)
    elif kind == 'conductor.stage_advanced':
        out = output if isinstance(output, dict) else {}
        for key in ('iteration', 'actions_run'):
            if key in out:
                shaped.setdefault(key, out[key])
    elif kind == 'tool_call':
        out = output if isinstance(output, dict) else {}
        for key in ('agent', 'tool', 'ok', 'handle', 'elapsed_s'):
            if key in out:
                if key == 'agent' and out[key] == 'researcher':
                    continue
                shaped.setdefault(key, out[key])
    return shaped


def _parse_json_object(value: Any) -> dict | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    candidates = [text]
    start, end = text.find('{'), text.rfind('}')
    if start >= 0 and end > start:
        candidates.insert(0, text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: '***' if any(s in k.lower() for s in ('api_key', 'token', 'password', 'secret')) else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value
