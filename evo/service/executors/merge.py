from __future__ import annotations

from evo.apply import GitWorkspace
from evo.apply.merge import merge_apply
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace

from .context import ExecCtx


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        ctx.report_start(tid)
    try:
        payload = cur.get('payload') or {}
        apply_id = payload.get('apply_id')
        if not apply_id:
            raise _store.StateError('MERGE_NO_APPLY', 'merge requires apply_id')
        result = merge_apply(
            apply_id=apply_id,
            workspace=GitWorkspace(ctx.cfg.storage.git_dir, ctx.cfg.chat_source),
            config=ctx.cfg,
            strategy=payload.get('strategy') or 'merge-commit',
        )
        ctx.update_payload(tid, {'result': result})
        thread_id = cur.get('thread_id')
        if thread_id:
            EventLog(ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).events_path) \
                .append(f'task:{tid}', 'merge.complete', result)
        ctx.report_success(tid, 'complete_merge')
    except Exception as exc:
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)
