from __future__ import annotations

from pathlib import Path

from evo.harness.plan import StopRequested
from evo.runtime.fs import load_json
from evo.service import state
from evo.service.thread_workspace import ThreadWorkspace

from .context import CancelToken, ExecCtx


class PipelineFailed(Exception):
    code = 'PIPELINE_FAILED'
    kind = 'permanent'


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = state.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        state.patch(ctx.store, tid, status='running')
    token = CancelToken(ctx, tid)
    try:
        _run_pipeline(ctx, tid, token)
    except StopRequested as exc:
        ctx.on_stop(tid, exc.at_step)
    except Exception as exc:
        ctx.on_failure(tid, exc)
    else:
        ctx.on_success(tid)
    finally:
        ctx.pop_thread(tid)


def _run_pipeline(ctx: ExecCtx, tid: str, token: CancelToken) -> None:
    from evo.harness.pipeline import build_standard_plan, PipelineOptions
    from evo.main import default_embed_provider, default_llm_provider
    from evo.runtime.session import create_session, session_scope

    cur = state.get(ctx.store, tid) or {}
    thread_id = cur.get('thread_id')
    payload = cur.get('payload') or {}
    eval_id = payload.get('eval_id')
    judge_path, trace_path = _resolve_corpus_paths(ctx, thread_id, eval_id)

    session = create_session(
        config=ctx.cfg, run_id=tid,
        llm_provider=default_llm_provider(ctx.cfg),
        embed_provider=default_embed_provider(ctx.cfg),
    )
    opts = PipelineOptions(**{k: payload[k]
                                for k in ('badcase_limit', 'score_field')
                                if k in payload})
    plan = build_standard_plan(
        opts,
        logger=session.logger('plan'),
        judge_path=judge_path, trace_path=trace_path,
    )
    with session_scope(session):
        result = plan.run(session, cancel_token=token)

    if not result.success:
        failed = [(o.name, o.error) for o in result.failed]
        raise PipelineFailed(f'pipeline failed at {failed}')

    paths = result.get('persist') or {}
    report_path = paths.get('report')
    if report_path is not None:
        data = load_json(report_path)
        rid = data.get('report_id') or Path(report_path).stem
        state.patch(ctx.store, tid, report_id=rid)


def _resolve_corpus_paths(ctx: ExecCtx, thread_id: str | None,
                            eval_id: str | None) -> tuple[Path | None, Path | None]:
    if not thread_id or not eval_id:
        return None, None
    ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
    judge = ws.eval_path(eval_id)
    bundle = ws.trace_bundle_path(eval_id)
    return (judge if judge.exists() else None,
             bundle if bundle.exists() else None)
