from __future__ import annotations

import logging
from typing import Any

from evo.datagen import run_eval, load_report, fetch_traces_for_report
from evo.orchestrator.llm import get_automodel
from evo.runtime.fs import atomic_write_json
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
        ctx.on_failure(tid, _store.StateError(
            'EVAL_NO_THREAD', 'eval flow requires a thread_id'))
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
            elog.append(f'task:{tid}', 'eval.run.start',
                         {'dataset_id': dataset_id, 'target': target_chat_url})
            report = run_eval(
                dataset_id=dataset_id,
                target_chat_url=target_chat_url or '',
                cfg=ctx.cfg,
                llm_factory=lambda: get_automodel(ctx.cfg.model_config.llm_role),
                max_workers=(payload.get('eval_options') or {}).get('max_workers', 10),
                dataset_name=(payload.get('eval_options') or {}).get('dataset_name', ''),
            )
            upstream_id = report.get('report_id')
            eval_id = upstream_id or eval_id or tid
            if not upstream_id:
                log.warning('eval %s upstream report_id missing, using %s',
                             tid, eval_id)
                elog.append(f'task:{tid}', 'eval.id.fallback',
                             {'used': eval_id,
                              'reason': 'upstream report_id missing'})
            report['report_id'] = eval_id
        else:
            if not eval_id:
                raise _store.StateError('EVAL_NO_TARGET',
                                        'need eval_id or dataset_id')
            elog.append(f'task:{tid}', 'eval.fetch.start', {'eval_id': eval_id})
            report = load_report(eval_id, ctx.cfg.storage.base_dir)
        atomic_write_json(ws.eval_path(eval_id), report)
        ctx.update_payload(tid, {'eval_id': eval_id})
        ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id) \
            .attach_artifact('eval_ids', eval_id)
        elog.append(f'task:{tid}', 'eval.ready',
                     {'eval_id': eval_id, 'cases': report.get('total_cases')})
        traces = _fetch_traces(tid, elog, report, token)
        if token.requested():
            ctx.on_stop(tid, 'fetch_traces')
            return
        atomic_write_json(ws.trace_bundle_path(eval_id), traces)
        elog.append(f'task:{tid}', 'eval.complete',
                     {'eval_id': eval_id, 'traces': len(traces)})
        ctx.on_success(tid)
    except Exception as exc:
        elog.append(f'task:{tid}', 'eval.failed', {'error': str(exc)})
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)


def _fetch_traces(tid: str, elog: EventLog, report: dict, token: CancelToken) -> dict[str, Any]:
    if token.requested():
        return {}
    out = fetch_traces_for_report(report, max_workers=8)
    for trace_id, trace in out.items():
        if isinstance(trace, dict) and trace.get('error'):
            elog.append(f'task:{tid}', 'trace.fetch_failed',
                        {'trace_id': trace_id, 'error': trace['error']})
    elog.append(f'task:{tid}', 'trace.bundle.ready', {'count': len(out)})
    return out
