from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from evo.harness.plan import StopRequested
from evo.runtime.fs import load_json
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace
from evo.utils import jsonable
from .context import CancelToken, ExecCtx


class PipelineFailed(Exception):
    code = 'PIPELINE_FAILED'
    kind = 'permanent'

    def __init__(self, message: str, details: dict | None = None) -> None:  # noqa: B042
        super().__init__(f'[{self.code}] {message}')
        self.message = message
        self.details = dict(details or {})


_STEPS_AFTER_INDEXER = ('indexer', 'conduct', 'synthesize', 'build_report', 'persist')


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        ctx.report_start(tid)
    token = CancelToken(ctx, tid)
    try:
        _run_pipeline(ctx, tid, token, resume=cur['status'] != 'queued')
    except StopRequested as exc:
        thread_id = (cur or {}).get('thread_id')
        if thread_id:
            EventLog(ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).events_path).append_event(
                'run.cancel', task_id=tid, payload={'at_step': exc.at_step}
            )
        ctx.on_stop(tid, exc.at_step)
    except Exception as exc:
        ctx.on_failure(tid, exc)
    else:
        ctx.on_success(tid)
    finally:
        ctx.pop_thread(tid)


def _run_pipeline(ctx: ExecCtx, tid: str, token: CancelToken, *, resume: bool = False) -> None:
    from evo.harness.pipeline import build_standard_plan, PipelineOptions
    from evo.main import default_embed_provider, default_llm_provider
    from evo.runtime.session import create_session, session_scope

    cur = _store.get(ctx.store, tid) or {}
    thread_id = cur.get('thread_id')
    payload = cur.get('payload') or {}
    eval_id = payload.get('eval_id')
    judge_path, trace_path = _resolve_corpus_paths(ctx, thread_id, eval_id)
    _write_revise_feedback(ctx, tid, payload.get('extra_instructions'))
    elog = EventLog(ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).events_path) if thread_id else None
    if elog:
        elog.append_event(
            'run.resume' if resume else 'run.start', task_id=tid, payload={'run_id': tid, 'eval_id': eval_id}
        )
    steps_dir = ctx.cfg.storage.runs_dir / tid / 'steps'
    if resume and steps_dir.exists():
        _invalidate_step_caches(steps_dir, _STEPS_AFTER_INDEXER)
    session = create_session(
        config=ctx.cfg,
        run_id=tid,
        thread_id=thread_id,
        llm_provider=default_llm_provider(ctx.cfg),
        embed_provider=default_embed_provider(ctx.cfg),
    )
    if elog:
        session.telemetry.event_writer = _event_writer(elog, tid)
    opts = PipelineOptions(**{k: payload[k] for k in ('badcase_limit', 'score_field') if k in payload})
    plan = build_standard_plan(opts, logger=session.logger('plan'), judge_path=judge_path, trace_path=trace_path)
    with session_scope(session):
        result = plan.run(session, cancel_token=token)
    if elog:
        _emit_step_results(elog, tid, result)
    if not result.success:
        failed = [(o.name, o.error) for o in result.failed]
        raise PipelineFailed(f'pipeline failed at {failed}', details={'failed_steps': failed})
    paths = result.get('persist') or {}
    report_path = paths.get('report')
    if report_path is not None:
        data = load_json(report_path)
        rid = data.get('report_id') or Path(report_path).stem
        ctx.update_payload(tid, {'report_id': rid})
        if thread_id:
            ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).attach_artifact('run_ids', tid)
        if elog:
            elog.append_event(
                'run.finish',
                task_id=tid,
                payload={'run_id': tid, 'eval_id': eval_id, 'report_id': rid, 'report_path': str(report_path)},
            )


def _invalidate_step_caches(steps_dir: Path, step_names: tuple[str, ...]) -> None:
    for name in step_names:
        pkl = steps_dir / f'{name}.pickle'
        if pkl.is_file():
            pkl.unlink()


def _write_revise_feedback(ctx: ExecCtx, tid: str, feedback: str | None) -> None:
    if not feedback:
        return
    path = ctx.cfg.storage.runs_dir / tid / 'revise_feedback.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'feedback': feedback}, ensure_ascii=False, indent=2), encoding='utf-8')


def _resolve_corpus_paths(ctx: ExecCtx, thread_id: str | None, eval_id: str | None) -> tuple[Path | None, Path | None]:
    if not thread_id or not eval_id:
        return (None, None)
    ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
    judge = ws.eval_path(eval_id)
    bundle = ws.trace_bundle_path(eval_id)
    return (judge if judge.exists() else None, bundle if bundle.exists() else None)


def _event_writer(elog: EventLog, task_id: str):
    def write(event_type: str, payload: dict[str, Any]) -> None:
        actor = payload.get('actor') or payload.get('agent')
        if event_type == 'researcher.tool_call.completed':
            elog.append_event(
                'run.tool.used',
                task_id=task_id,
                payload={
                    'agent': actor,
                    'tool': payload.get('tool'),
                    'round': payload.get('round'),
                    'input_summary': _summary(payload.get('args')),
                    'output_summary': payload.get('summary') or _summary(payload.get('output')),
                    'ok': payload.get('ok'),
                    'elapsed_s': payload.get('elapsed_s'),
                },
            )
        elif event_type == 'researcher.reasoning_summary':
            elog.append_event(
                'run.researcher.result',
                task_id=task_id,
                payload={
                    'agent': actor,
                    'rounds': payload.get('rounds'),
                    'tool_calls': payload.get('tool_calls'),
                    'result_summary': _summary(payload.get('final_answer'), limit=1200),
                },
            )
        elif event_type == 'conductor.decision':
            decision = payload.get('decision') or {}
            elog.append_event(
                'run.conductor.result',
                task_id=task_id,
                payload={
                    'iteration': payload.get('iteration'),
                    'actions': decision.get('actions') if isinstance(decision, dict) else None,
                    'done': decision.get('done') if isinstance(decision, dict) else None,
                    'summary': _summary(decision, limit=1200),
                },
            )

    return write


def _emit_step_results(elog: EventLog, task_id: str, result) -> None:
    indexer = result.get('indexer')
    if indexer is not None:
        elog.append_event(
            'run.indexer.result',
            task_id=task_id,
            payload={
                'status': _step_status(result, 'indexer'),
                'summary': _summary(indexer, limit=1600),
                'result': _compact(indexer),
            },
        )
    conduct = result.get('conduct')
    if conduct is not None:
        elog.append_event(
            'run.conductor.result',
            task_id=task_id,
            payload={
                'status': _step_status(result, 'conduct'),
                'summary': _summary(conduct, limit=1200),
                'result': _compact(conduct),
            },
        )


def _step_status(result, name: str) -> str | None:
    for outcome in result.outcomes:
        if outcome.name == name:
            return outcome.status
    return None


def _compact(value: Any, *, limit: int = 4000) -> Any:
    data = jsonable(value)
    text = _summary(data, limit=limit)
    if isinstance(data, (dict, list)) and len(text) < limit:
        return data
    return text


def _summary(value: Any, *, limit: int = 800) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        text = value
    else:
        import json

        text = json.dumps(jsonable(value), ensure_ascii=False, default=str)
    text = ' '.join(text.split())
    return text[:limit]
