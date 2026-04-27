from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from evo.service.core import store
from evo.service.core.errors import StateError
from evo.service.core import schemas
from evo.orchestrator import capabilities as caps

if TYPE_CHECKING:
    from evo.service.core.manager import JobManager

_log = logging.getLogger('evo.service.core.ops_executor')

OpHandler = Callable[['JobManager', dict], 'OpResult']


@dataclass
class Op:
    op: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpResult:
    op: str
    task_id: str | None = None
    status: str = 'pending'
    error: dict | None = None
    data: dict | None = None


class OpsExecutor:
    def __init__(self, jm: JobManager) -> None:
        self._jm = jm

    def execute(self, ops: list[Op], *, thread_id: str | None = None,
                idem_key: str | None = None) -> list[OpResult]:
        results: list[OpResult] = []
        for op in ops:
            try:
                caps.validate(op.op, op.args)
            except ValueError as exc:
                results.append(OpResult(op=op.op, status='rejected',
                                         error={'code': 'VALIDATION_ERROR',
                                                'message': str(exc)}))
                continue
            args = dict(op.args)
            if thread_id:
                args['thread_id'] = thread_id
            args = _validate_args(op.op, args)
            handler = OP_HANDLERS.get(op.op)
            if handler is None:
                results.append(OpResult(op=op.op, status='unknown',
                                         error={'code': 'UNSUPPORTED_OP',
                                                'message': f'{op.op} not implemented'}))
                continue
            try:
                result = handler(self._jm, args)
                results.append(result)
            except Exception as exc:
                _log.exception('op %s failed: %s', op.op, exc)
                results.append(OpResult(op=op.op, status='failed',
                                         error={'code': getattr(exc, 'code', 'EXEC_ERROR'),
                                                'message': str(exc)}))
        return results


def _start_result(op: str, tid: str) -> OpResult:
    return OpResult(op=op, task_id=tid, status='submitted')


def _task_op_result(op: str, tid: str, status: str, data: dict | None = None) -> OpResult:
    return OpResult(op=op, task_id=tid, status=status, data=data)


def _h_run_start(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_run(**args)
    return _start_result('run.start', tid)


def _h_run_stop(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('run.stop', tid, 'stopped', jm.stop(tid))


def _h_run_continue(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('run.continue', tid, 'continued', jm.cont(tid))


def _h_run_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('run.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_task_stop_active(jm: JobManager, args: dict) -> OpResult:
    tid = _resolve_active_task(jm, args, require_running=True)
    row = jm.stop(tid)
    return _task_op_result('task.stop_active', tid, 'stopped', row)


def _h_task_cancel_active(jm: JobManager, args: dict) -> OpResult:
    tid = _resolve_active_task(jm, args)
    row = jm.cancel(tid)
    return _task_op_result('task.cancel_active', tid, 'cancelled', row)


def _h_task_continue_latest(jm: JobManager, args: dict) -> OpResult:
    tid = args.get('task_id') or _resolve_latest_resumable_task(jm, args)
    row = jm.cont(tid)
    return _task_op_result('task.continue_latest', tid, 'continued', row)


def _h_apply_start(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_apply(**args)
    return _start_result('apply.start', tid)


def _h_apply_stop(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('apply.stop', tid, 'stopped', jm.stop(tid))


def _h_apply_continue(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('apply.continue', tid, 'continued', jm.cont(tid))


def _h_apply_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('apply.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_apply_accept(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    auto_next = args.pop('auto_next', 'none')
    row = jm.accept(tid, auto_next=auto_next)
    return _task_op_result('apply.accept', tid, 'accepted', row)


def _h_apply_reject(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('apply.reject', tid, 'rejected', jm.reject(tid))


def _h_eval_run(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_eval(**args)
    return _start_result('eval.run', tid)


def _h_eval_fetch(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_eval(**args)
    return _start_result('eval.fetch', tid)


def _h_eval_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('eval.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_abtest_create(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_abtest(**args)
    return _start_result('abtest.create', tid)


def _h_abtest_stop(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('abtest.stop', tid, 'stopped', jm.stop(tid))


def _h_abtest_continue(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('abtest.continue', tid, 'continued', jm.cont(tid))


def _h_abtest_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('abtest.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_dataset_gen_start(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_dataset_gen(**args)
    return _start_result('dataset_gen.start', tid)


def _h_dataset_gen_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('dataset_gen.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_merge_start(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_merge(**args)
    return _start_result('merge.start', tid)


def _h_merge_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('merge.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_deploy_start(jm: JobManager, args: dict) -> OpResult:
    tid = jm.submit_deploy(**args)
    return _start_result('deploy.start', tid)


def _h_deploy_continue(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('deploy.continue', tid, 'continued', jm.cont(tid))


def _h_deploy_cancel(jm: JobManager, args: dict) -> OpResult:
    tid = args['task_id']
    return _task_op_result('deploy.cancel', tid, 'cancelled', jm.cancel(tid))


def _h_checkpoint_list_pending(jm: JobManager, args: dict) -> OpResult:
    thread_id = args.get('thread_id')
    if not thread_id:
        raise StateError('CHECKPOINT_NO_THREAD', 'thread_id is required')
    from evo.service.threads.workspace import CheckpointStore, EventLog, ThreadWorkspace
    ws = ThreadWorkspace(jm.config.storage.base_dir, thread_id)
    elog = EventLog(ws.events_path)
    cps = CheckpointStore(ws, elog)
    pending = cps.list_pending()
    return OpResult(op='checkpoint.list_pending', status='ok',
                     data={'checkpoints': pending, 'count': len(pending)})


def _h_checkpoint_respond(jm: JobManager, args: dict) -> OpResult:
    cp_id = args.get('cp_id')
    choice = args.get('choice', 'approve')
    feedback = args.get('feedback')
    if not cp_id:
        raise StateError('CHECKPOINT_NO_CP_ID', 'cp_id is required')
    if choice not in ('approve', 'revise', 'cancel'):
        raise StateError('CHECKPOINT_BAD_CHOICE',
                         f'choice must be approve/revise/cancel, got {choice!r}')
    thread_id = args.get('thread_id')
    if not thread_id:
        raise StateError('CHECKPOINT_NO_THREAD', 'thread_id is required')
    from evo.service.threads.workspace import CheckpointStore, EventLog, ThreadWorkspace
    ws = ThreadWorkspace(jm.config.storage.base_dir, thread_id)
    elog = EventLog(ws.events_path)
    cps = CheckpointStore(ws, elog)
    rec = cps.respond(cp_id, choice=choice, feedback=feedback)
    task_id = rec.get('task_id')
    if task_id and choice in ('approve', 'revise'):
        task_row = store.get(jm.store, task_id)
        if task_row and task_row.get('status') == 'paused':
            jm.cont(task_id)
    return OpResult(op='checkpoint.respond', task_id=task_id,
                     status='responded', data=rec)


OP_HANDLERS: dict[str, OpHandler] = {}

for _h in [
    _h_run_start, _h_run_stop, _h_run_continue, _h_run_cancel,
    _h_task_stop_active, _h_task_cancel_active, _h_task_continue_latest,
    _h_apply_start, _h_apply_stop, _h_apply_continue, _h_apply_cancel,
    _h_apply_accept, _h_apply_reject,
    _h_eval_run, _h_eval_fetch, _h_eval_cancel,
    _h_abtest_create, _h_abtest_stop, _h_abtest_continue, _h_abtest_cancel,
    _h_merge_start, _h_merge_cancel,
    _h_deploy_start, _h_deploy_continue, _h_deploy_cancel,
    _h_checkpoint_list_pending, _h_checkpoint_respond,
]:
    name = _h.__name__.replace('_h_', '', 1).replace('_', '.', 1)
    OP_HANDLERS[name] = _h

OP_HANDLERS['dataset_gen.start'] = _h_dataset_gen_start
OP_HANDLERS['dataset_gen.cancel'] = _h_dataset_gen_cancel


def _validate_args(op: str, args: dict[str, Any]) -> dict[str, Any]:
    model_by_op = {
        'run.start': schemas.RunCreate,
        'apply.start': schemas.ApplyCreate,
        'dataset_gen.start': schemas.DatasetGenCreate,
        'eval.run': schemas.EvalCreate,
        'eval.fetch': schemas.EvalCreate,
        'merge.start': schemas.MergeCreate,
        'deploy.start': schemas.DeployCreate,
        'abtest.create': schemas.AbtestCreate,
    }
    model = model_by_op.get(op)
    if model is None:
        return args
    return model(**args).model_dump(exclude_none=True)


_FLOW_PRIORITY = ('run', 'apply', 'eval', 'dataset_gen', 'abtest', 'deploy', 'merge')


def _resolve_active_task(jm: JobManager, args: dict[str, Any], *,
                         require_running: bool = False) -> str:
    thread_id = args.get('thread_id')
    flow = args.get('flow')
    flows = (flow,) if flow else _FLOW_PRIORITY
    for fl in flows:
        rows = store.list_active(jm.store, fl, scope='thread' if thread_id else 'global',
                                 thread_id=thread_id)
        candidates = [
            r for r in rows
            if (r.get('status') == 'running' if require_running else True)
        ]
        if candidates:
            order = {'running': 0, 'queued': 1, 'stopping': 2,
                     'paused': 3, 'failed_transient': 4}
            candidates.sort(key=lambda r: (
                order.get(r.get('status'), 99), -float(r.get('created_at', 0) or 0),
            ))
            return candidates[0]['id']
    raise StateError('NO_ACTIVE_TASK', f'no active task found for flow={flow!r}')


def _resolve_latest_resumable_task(jm: JobManager, args: dict[str, Any]) -> str:
    thread_id = args.get('thread_id')
    flow = args.get('flow')
    flows = (flow,) if flow else _FLOW_PRIORITY
    best: dict | None = None
    for fl in flows:
        rows = (store.list_flow_tasks_by_thread(jm.store, fl, thread_id)
                if thread_id else store.list_recent(jm.store, fl, 100))
        for row in rows:
            if row.get('status') not in ('paused', 'failed_transient'):
                continue
            if best is None or row.get('updated_at', 0) > best.get('updated_at', 0):
                best = row
    if best:
        return best['id']
    raise StateError('NO_RESUMABLE_TASK', f'no paused or transient failed task found for flow={flow!r}')
