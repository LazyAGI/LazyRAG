from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from evo.service.core import store as _store

POLL_INTERVAL_S = 0.5


def _is_terminal(st: _store.FsStateStore, task_id: str) -> bool:
    row = _store.get(st, task_id)
    if row is None:
        return True
    return row['status'] in _store.terminal_for(row['flow'])


async def tail_jsonl(st: _store.FsStateStore, task_id: str, path: Path,
                     *, since_offset: int = 0) -> AsyncIterator[dict]:
    offset = since_offset
    while True:
        if path.exists():
            size = path.stat().st_size
            if size > offset:
                with path.open('rb') as f:
                    f.seek(offset)
                    chunk = f.read(size - offset)
                offset = size
                for line in chunk.splitlines():
                    text = line.decode('utf-8', 'replace').strip()
                    if text:
                        yield {'event': 'message', 'data': text}
        if _is_terminal(st, task_id):
            yield {'event': 'terminal', 'data': f'{{"task_id":"{task_id}"}}'}
            return
        await asyncio.sleep(POLL_INTERVAL_S)


async def tail_events(path: Path, *, since_seq: int = 0) -> AsyncIterator[dict]:
    """Tail events.jsonl by seq number instead of byte offset."""
    import json
    last_seq = since_seq
    while True:
        if path.exists():
            with path.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    seq = obj.get('seq', 0)
                    if seq > last_seq:
                        last_seq = seq
                        yield {'event': obj.get('kind', 'message'), 'data': line}
        await asyncio.sleep(POLL_INTERVAL_S)
