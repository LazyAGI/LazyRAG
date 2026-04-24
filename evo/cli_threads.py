from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from evo.runtime.config import EvoConfig
from evo.service import jobs
from evo.service.threads import ThreadCreate, ThreadHub


def build_thread_hub(cfg: EvoConfig) -> ThreadHub:
    from evo.orchestrator.llm import make_evo_llm

    jm = jobs.get_manager(cfg)
    return ThreadHub(jm=jm, cfg=cfg, llm_factory=make_evo_llm(cfg))


async def run_auto_cli(
    hub: ThreadHub,
    *,
    inputs: dict[str, Any],
    timeout_s: float,
    poll_s: float = 2.0,
) -> int:
    log = logging.getLogger('evo.main')
    meta = hub.create_thread(ThreadCreate(mode='auto', inputs=inputs))
    tid = meta['id']
    log.info('auto thread %s started (timeout=%ss)', tid, timeout_s)
    deadline = time.monotonic() + timeout_s
    last_reason = ''
    while True:
        op = hub.auto(tid)
        if op is None:
            log.error('auto operator missing for %s', tid)
            return 1
        task = getattr(op, '_task', None)
        lt = op.last_turn
        cur = (lt.user_message or lt.trigger or '') if lt else ''
        if lt and cur != last_reason:
            last_reason = cur
            log.info('auto: %s', last_reason)
        if task is not None and task.done():
            exc = task.exception()
            if exc is not None:
                if isinstance(exc, asyncio.CancelledError):
                    log.warning('auto task cancelled')
                    return 1
                log.error('auto task failed: %s', exc, exc_info=exc)
                return 1
            log.info('auto thread %s finished normally', tid)
            return 0
        if time.monotonic() >= deadline:
            log.error('auto thread %s timed out after %ss', tid, timeout_s)
            await hub.stop_thread(tid)
            return 1
        await asyncio.sleep(poll_s)


async def run_chat_cli(
    hub: ThreadHub,
    *,
    message: str,
    thread_id: str | None,
) -> int:
    log = logging.getLogger('evo.main')
    if thread_id:
        tid = thread_id
        ws = hub.workspace(tid)
        if not ws.thread_meta_path.exists():
            log.error('thread not found: %s', tid)
            return 1
        meta = json.loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        if meta.get('mode') != 'interactive':
            log.error('thread %s is not interactive (mode=%r)', tid,
                      meta.get('mode'))
            return 1
    else:
        meta = hub.create_thread(ThreadCreate(mode='interactive'))
        tid = meta['id']
        log.info('interactive thread %s', tid)

    err = False
    async for ev in hub.post_message(tid, message):
        event = ev.get('event', '')
        raw = ev.get('data', '')
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            payload = {'raw': raw}
        if event == 'error':
            log.error('agent error: %s', payload)
            err = True
            continue
        text = payload.get('text', '')
        if text:
            print(text, end='', flush=True)
        elif payload:
            print(f'[{event}] {json.dumps(payload, ensure_ascii=False)}')
    if err:
        return 1
    print()
    return 0


def run_decide_cli(hub: ThreadHub, *, inputs: dict[str, Any]) -> int:
    log = logging.getLogger('evo.main')
    meta = hub.create_thread(
        ThreadCreate(mode='auto', inputs=inputs, start_auto=False))
    tid = meta['id']

    async def _one() -> Any:
        return await hub.ensure_auto(tid).step_once()

    d = asyncio.run(_one())
    print(json.dumps(d.to_dict(), ensure_ascii=False, indent=2))
    log.info('thread %s step_once done', tid)
    return 0
