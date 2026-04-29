from __future__ import annotations

import logging
from typing import Any

from evo.datagen import run_generate_pipeline
from evo.datagen.kb_client import KBClient
from evo.orchestrator.llm import get_automodel
from evo.runtime.fs import atomic_write_json
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace

from .context import CancelToken, ExecCtx

log = logging.getLogger('evo.service.executors.dataset_gen')


def _resolve_llm_factory(cfg):
    role = cfg.model_config.llm_role
    def factory():
        return get_automodel(role)
    return factory


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        ctx.report_start(tid)
    thread_id = cur.get('thread_id')
    payload = cur.get('payload') or {}
    kb_id = payload.get('kb_id')
    algo_id = payload.get('algo_id', 'general_algo')
    eval_name = payload.get('eval_name', tid)
    num_cases = payload.get('num_cases')
    if not kb_id:
        ctx.on_failure(tid, _store.StateError(
            'DATASET_NO_KB', 'dataset_gen requires kb_id'))
        return
    token = CancelToken(ctx, tid)
    elog = EventLog(ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).events_path) if thread_id else None
    try:
        if elog:
            elog.append_event('dataset_gen.start', task_id=tid, payload={
                'dataset_id': eval_name,
                'kb_id': kb_id,
                'algo_id': algo_id,
                'num_cases': num_cases,
            })
        ds = KBClient.from_config(ctx.cfg)
        llm_factory = _resolve_llm_factory(ctx.cfg)
        path, data = run_generate_pipeline(
            kb_id=kb_id, algo_id=algo_id, eval_name=eval_name,
            dataset_source=ds, config=ctx.cfg, thread_id=thread_id,
            llm_factory=llm_factory, cancel=token.requested,
            num_cases=num_cases,
            on_progress=(lambda current, total: elog.append_event(
                'dataset_gen.progress', task_id=tid,
                payload={'current': current, 'total': total, 'dataset_id': eval_name})
                if elog else None))
        ctx.update_payload(tid, {'dataset_path': path})
        if thread_id:
            ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id) \
                .attach_artifact('dataset_ids', eval_name)
            elog.append_event('dataset_gen.finish', task_id=tid, payload={
                'dataset_id': eval_name,
                'path': path,
                'cases': data.get('total_nums'),
            })
        ctx.on_success(tid)
    except Exception as exc:
        if elog and token.requested():
            elog.append_event('dataset_gen.cancel', task_id=tid, payload={'dataset_id': eval_name})
        log.exception('dataset_gen %s failed: %s', tid, exc)
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)
