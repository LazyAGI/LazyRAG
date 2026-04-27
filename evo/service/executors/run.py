from __future__ import annotations

import json
from pathlib import Path

from evo.harness.plan import StopRequested
from evo.runtime.fs import load_json
from evo.service.core import store as _store
from evo.service.threads.workspace import CheckpointStore, EventLog, ThreadWorkspace

from .context import CancelToken, ExecCtx


class PipelineFailed(Exception):
    code = 'PIPELINE_FAILED'
    kind = 'permanent'

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(f'[{self.code}] {message}')
        self.message = message
        self.details = dict(details or {})


_STEPS_AFTER_INDEXER = ('indexer', 'conduct', 'synthesize', 'build_report', 'persist')

_CHECKPOINTABLE_STEPS = {
    'indexer': 'pre_indexer_review',
}


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
        ctx.on_stop(tid, exc.at_step)
    except Exception as exc:
        ctx.on_failure(tid, exc)
    else:
        ctx.on_success(tid)
    finally:
        ctx.pop_thread(tid)


def _run_pipeline(ctx: ExecCtx, tid: str, token: CancelToken,
                  *, resume: bool = False) -> None:
    from evo.harness.pipeline import build_standard_plan, PipelineOptions
    from evo.main import default_embed_provider, default_llm_provider
    from evo.runtime.session import create_session, session_scope

    cur = _store.get(ctx.store, tid) or {}
    thread_id = cur.get('thread_id')
    payload = cur.get('payload') or {}
    eval_id = payload.get('eval_id')
    judge_path, trace_path = _resolve_corpus_paths(ctx, thread_id, eval_id)

    steps_dir = ctx.cfg.storage.runs_dir / tid / 'steps'
    if resume and steps_dir.exists():
        _invalidate_step_caches(steps_dir, _STEPS_AFTER_INDEXER)

    session = create_session(
        config=ctx.cfg, run_id=tid,
        llm_provider=default_llm_provider(ctx.cfg),
        embed_provider=default_embed_provider(ctx.cfg),
    )
    opts = PipelineOptions(**{k: payload[k]
                                for k in ('badcase_limit', 'score_field')
                                if k in payload})

    cp_hook = _make_checkpoint_hook(ctx, tid, thread_id, session) \
        if thread_id else None

    plan = build_standard_plan(
        opts,
        logger=session.logger('plan'),
        judge_path=judge_path, trace_path=trace_path,
        before_step=cp_hook,
    )
    with session_scope(session):
        result = plan.run(session, cancel_token=token)

    if not result.success:
        failed = [(o.name, o.error) for o in result.failed]
        raise PipelineFailed(f'pipeline failed at {failed}',
                             details={'failed_steps': failed})

    paths = result.get('persist') or {}
    report_path = paths.get('report')
    if report_path is not None:
        data = load_json(report_path)
        rid = data.get('report_id') or Path(report_path).stem
        ctx.update_payload(tid, {'report_id': rid})


def _invalidate_step_caches(steps_dir: Path, step_names: tuple[str, ...]) -> None:
    for name in step_names:
        pkl = steps_dir / f'{name}.pickle'
        if pkl.is_file():
            pkl.unlink()


def _read_thread_mode(base_dir, thread_id: str) -> str:
    meta_path = Path(base_dir) / 'state' / 'threads' / thread_id / 'thread.json'
    try:
        return json.loads(meta_path.read_text(encoding='utf-8')).get('mode', 'interactive')
    except Exception:
        return 'interactive'


def _make_checkpoint_hook(ctx: ExecCtx, tid: str, thread_id: str | None,
                           session) -> Callable[[str, any], None] | None:
    if not thread_id:
        return None
    mode = _read_thread_mode(ctx.cfg.storage.base_dir, thread_id)
    if mode != 'interactive':
        return None
    ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
    elog = EventLog(ws.events_path)
    cps = CheckpointStore(ws, elog)
    _fired: set[str] = set()

    def hook(step_name: str, step_ctx) -> None:
        if step_name not in _CHECKPOINTABLE_STEPS or step_name in _fired:
            return
        _fired.add(step_name)
        kind = _CHECKPOINTABLE_STEPS[step_name]
        payload = _build_checkpoint_payload(step_name, session)
        title = _build_checkpoint_title(step_name)
        cp_id = cps.create(
            task_id=tid, kind=kind, title=title,
            payload=payload,
            options=['approve', 'revise', 'cancel'],
            default='approve',
        )
        try:
            rec = cps.wait(cp_id, cancel_token=lambda: ctx.is_cancelled(tid),
                           timeout_s=None)
        except Exception:
            raise StopRequested(at_step=f'{step_name}_checkpoint')
        choice = (rec.get('response') or {}).get('choice', 'approve')
        if choice == 'cancel':
            raise StopRequested(at_step=f'{step_name}_checkpoint_cancelled')
        if choice == 'revise':
            feedback = (rec.get('response') or {}).get('feedback', '')
            _write_revise_feedback(ctx.cfg.storage.runs_dir, tid, step_name, feedback)
            steps_dir = ctx.cfg.storage.runs_dir / tid / 'steps'
            _invalidate_step_caches(steps_dir, _STEPS_AFTER_INDEXER)
            _fired.difference_update(set(_CHECKPOINTABLE_STEPS) - {step_name})

    return hook


def _build_checkpoint_title(step_name: str) -> str:
    titles = {
        'indexer': 'Review analysis direction before generating hypotheses',
    }
    return titles.get(step_name, f'Review before {step_name} step')


def _build_checkpoint_payload(step_name: str, session) -> dict:
    if step_name == 'indexer':
        cg = session.clustering_global
        return {
            'step': step_name,
            'summary': {
                'total_cases': len(session.parsed_judge),
                'clusters': [
                    {'id': cs.cluster_id, 'size': cs.size}
                    for cs in (cg.cluster_summaries if cg else [])
                ],
            },
            'hint': 'review the analysis direction; you may approve, revise with feedback, or cancel',
        }
    return {
        'step': step_name,
        'hint': 'review the current step direction',
    }


def _write_revise_feedback(runs_dir: Path, tid: str, step_name: str,
                            feedback: str) -> None:
    path = runs_dir / tid / 'revise_feedback.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'task_id': tid,
        'step': step_name,
        'feedback': feedback,
        'created_at': __import__('time').time(),
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def _resolve_corpus_paths(ctx: ExecCtx, thread_id: str | None,
                            eval_id: str | None) -> tuple[Path | None, Path | None]:
    if not thread_id or not eval_id:
        return None, None
    ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
    judge = ws.eval_path(eval_id)
    bundle = ws.trace_bundle_path(eval_id)
    return (judge if judge.exists() else None,
             bundle if bundle.exists() else None)
