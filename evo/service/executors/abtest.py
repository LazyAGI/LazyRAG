from __future__ import annotations

from pathlib import Path

from evo.abtest import AbtestInputs, VerdictPolicy, execute_abtest
from evo.orchestrator.llm import get_automodel
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace

from .context import CancelToken, ExecCtx


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        ctx.report_start(tid)
    thread_id = cur.get('thread_id')
    if not thread_id:
        ctx.on_failure(tid, _store.StateError(
            'ABTEST_NO_THREAD', 'abtest flow requires a thread_id'))
        return
    payload = cur.get('payload') or {}
    ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
    elog = EventLog(ws.events_path)
    runner = ctx.chat_runner_factory()
    token = CancelToken(ctx, tid)
    policy_data = payload.get('policy') or {}
    if isinstance(policy_data.get('guard_metrics'), list):
        policy_data['guard_metrics'] = tuple(policy_data['guard_metrics'])
    inputs = AbtestInputs(
        abtest_id=tid, thread_id=thread_id,
        apply_id=payload['apply_id'],
        baseline_eval_id=payload['baseline_eval_id'],
        dataset_id=payload['dataset_id'],
        apply_worktree=Path(payload['apply_worktree']),
        eval_options=payload.get('eval_options') or {},
        policy=ctx.abtest_policy.get(tid) or VerdictPolicy(**policy_data),
    )
    try:
        result = execute_abtest(
            inputs=inputs, workspace=ws, log=elog,
            chat_runner=runner, chat_registry=ctx.chat_registry,
            cfg=ctx.cfg,
            llm_factory=lambda: get_automodel(ctx.cfg.model_config.llm_role),
            cancel=token.requested,
        )
        ctx.update_payload(tid,
                            {'verdict': result.verdict,
                             'candidate_chat_id': result.candidate_chat_id,
                             'new_eval_id': result.new_eval_id})
        if result.status == 'succeeded':
            ctx.on_success(tid)
        elif result.status == 'cancelled':
            ctx.on_stop(tid, 'abtest')
        else:
            ctx.on_failure(tid, RuntimeError(result.error or 'abtest failed'))
    except Exception as exc:
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)
        ctx.abtest_policy.pop(tid, None)
