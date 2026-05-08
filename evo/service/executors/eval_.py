from __future__ import annotations
import hashlib
import logging
import os
from dataclasses import replace
from typing import Any
from evo.datagen import run_eval, load_report, fetch_traces_for_report
from evo.orchestrator.llm import get_automodel
from evo.runtime.fs import atomic_write_json
from evo.runtime.model_gateway import ModelGateway
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace
from .context import CancelToken, ExecCtx

log = logging.getLogger('evo.service.executors.eval')


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        ctx.report_start(tid)
    thread_id = cur.get('thread_id')
    if not thread_id:
        ctx.on_failure(tid, _store.StateError('EVAL_NO_THREAD', 'eval flow requires a thread_id'))
        return
    payload = cur.get('payload') or {}
    eval_id = payload.get('eval_id')
    dataset_id = payload.get('dataset_id')
    target_chat_url = payload.get('target_chat_url')
    ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
    elog = EventLog(ws.events_path)
    token = CancelToken(ctx, tid)
    try:
        if dataset_id:
            elog.append_event(
                'eval.start', task_id=tid, payload={'dataset_id': dataset_id, 'target_chat_url': target_chat_url}
            )
            report = run_eval(
                dataset_id=dataset_id,
                target_chat_url=target_chat_url or '',
                cfg=ctx.cfg,
                llm_factory=_eval_judge_llm_factory(ctx),
                max_workers=(payload.get('eval_options') or {}).get('max_workers', 10),
                dataset_name=(payload.get('eval_options') or {}).get('dataset_name', ''),
                filters=(payload.get('eval_options') or {}).get('filters') or {},
                persist_report=False,
                on_progress=lambda current, total: elog.append_event(
                    'eval.progress',
                    task_id=tid,
                    payload={'phase': 'rag', 'current': current, 'total': total, 'dataset_id': dataset_id},
                ),
                on_judge_progress=lambda current, total: elog.append_event(
                    'eval.progress',
                    task_id=tid,
                    payload={'phase': 'judge', 'current': current, 'total': total, 'dataset_id': dataset_id},
                ),
            )
            upstream_id = report.get('report_id')
            eval_id = upstream_id or eval_id or tid
            if not upstream_id:
                log.warning('eval %s upstream report_id missing, using %s', tid, eval_id)
            report['report_id'] = eval_id
        else:
            if not eval_id:
                raise _store.StateError('EVAL_NO_TARGET', 'need eval_id or dataset_id')
            elog.append_event('eval.start', task_id=tid, payload={'eval_id': eval_id})
            report = load_report(eval_id, ctx.cfg.storage.base_dir)
        atomic_write_json(ws.eval_path(eval_id), report)
        ctx.update_payload(tid, {'eval_id': eval_id})
        ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).attach_artifact('eval_ids', eval_id)
        traces = _fetch_traces(tid, elog, report, token)
        if token.requested():
            elog.append_event('eval.cancel', task_id=tid, payload={'eval_id': eval_id})
            ctx.on_stop(tid, 'fetch_traces')
            return
        atomic_write_json(ws.trace_bundle_path(eval_id), traces)
        elog.append_event(
            'eval.finish',
            task_id=tid,
            payload={'eval_id': eval_id, 'cases': report.get('total_cases'), 'traces': len(traces)},
        )
        ctx.on_success(tid)
    except Exception as exc:
        if token.requested():
            elog.append_event('eval.cancel', task_id=tid, payload={'eval_id': eval_id, 'dataset_id': dataset_id})
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)


def _fetch_traces(tid: str, elog: EventLog, report: dict, token: CancelToken) -> dict[str, Any]:
    if token.requested():
        return {}
    out = fetch_traces_for_report(report, max_workers=8)
    return out


def _eval_judge_llm_factory(ctx: ExecCtx):
    timeout_s = float(os.getenv('EVO_EVAL_JUDGE_TIMEOUT_S', '120'))
    max_retries = int(os.getenv('EVO_EVAL_JUDGE_MAX_RETRIES', '1'))
    cfg = replace(ctx.cfg.llm, producer_timeout_s=timeout_s, max_retries=max_retries)
    gateway: ModelGateway[str] = ModelGateway(
        cfg, name='evo-eval-judge-llm', logger=logging.getLogger('evo.datagen.evaluate')
    )
    client = get_automodel(ctx.cfg.model_config.llm_role)

    def factory():
        def call(prompt: str):
            digest = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            return gateway.call(lambda: client(prompt), cache_key=f'eval-judge:{digest}', agent='eval_judge')

        return call

    return factory
