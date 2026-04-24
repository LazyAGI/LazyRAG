from __future__ import annotations

import logging
from typing import Any

from evo.providers import (
    CachedTraceProvider, TraceCache, TraceProvider, write_bundle,
)
from evo.runtime.fs import atomic_write_json
from evo.service import state
from evo.service.thread_workspace import EventLog, ThreadWorkspace

from .context import CancelToken, ExecCtx

log = logging.getLogger('evo.service.executors.eval')


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = state.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        state.patch(ctx.store, tid, status='running')
    thread_id = cur.get('thread_id')
    if not thread_id:
        ctx.on_failure(tid, state.StateError(
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
        ep = ctx.eval_provider_factory()
        tp = CachedTraceProvider(ctx.trace_provider_factory(),
                                   _trace_cache(ctx))
        if dataset_id:
            elog.append(f'task:{tid}', 'eval.run.start',
                         {'dataset_id': dataset_id, 'target': target_chat_url})
            report = ep.run_eval(dataset_id=dataset_id,
                                  target_chat_url=target_chat_url or '',
                                  options=payload.get('eval_options') or None)
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
                raise state.StateError('EVAL_NO_TARGET',
                                        'need eval_id or dataset_id')
            elog.append(f'task:{tid}', 'eval.fetch.start', {'eval_id': eval_id})
            report = ep.get_eval_report(eval_id)
        atomic_write_json(ws.eval_path(eval_id), report)
        state.patch(ctx.store, tid, payload={**payload, 'eval_id': eval_id})
        ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id) \
            .attach_artifact('eval_ids', eval_id)
        elog.append(f'task:{tid}', 'eval.ready',
                     {'eval_id': eval_id, 'cases': report.get('total_cases')})
        traces = _fetch_traces(tid, elog, tp, report, token)
        if token.requested():
            ctx.on_stop(tid, 'fetch_traces')
            return
        write_bundle(ws.trace_bundle_path(eval_id), traces)
        elog.append(f'task:{tid}', 'eval.complete',
                     {'eval_id': eval_id, 'traces': len(traces)})
        state.transition(ctx.store, tid, 'finish', current_step='complete')
    except Exception as exc:
        elog.append(f'task:{tid}', 'eval.failed', {'error': str(exc)})
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)


def _trace_cache(ctx: ExecCtx) -> TraceCache:
    return TraceCache(ctx.cfg.storage.base_dir / 'state' / 'traces')


def _fetch_traces(tid: str, elog: EventLog, tp: TraceProvider,
                   report: dict, token: CancelToken) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for case in report.get('case_details') or []:
        if token.requested():
            return out
        trace_id = case.get('trace_id')
        if not trace_id or trace_id in out:
            continue
        try:
            out[trace_id] = tp.get_trace(trace_id)
        except Exception as exc:
            elog.append(f'task:{tid}', 'trace.fetch_failed',
                         {'trace_id': trace_id, 'error': str(exc)})
    elog.append(f'task:{tid}', 'trace.bundle.ready', {'count': len(out)})
    return out
