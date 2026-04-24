from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from evo.service import state

POLL_INTERVAL_S = 0.5


def _is_terminal(store: state.FsStateStore, task_id: str) -> bool:
    row = state.get(store, task_id)
    if row is None:
        return True
    return row['status'] in state.terminal_for(row['flow'])


async def tail_jsonl(store: state.FsStateStore, task_id: str, path: Path,
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
        if _is_terminal(store, task_id):
            yield {'event': 'terminal', 'data': f'{{"task_id":"{task_id}"}}'}
            return
        await asyncio.sleep(POLL_INTERVAL_S)
