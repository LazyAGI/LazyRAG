from __future__ import annotations

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
            args = _validate_args(op.op, dict(op.args))
            if thread_id:
                args['thread_id'] = thread_id
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


OP_HANDLERS: dict[str, OpHandler] = {}

for _h in [
    _h_run_start, _h_run_stop, _h_run_continue, _h_run_cancel,
    _h_apply_start, _h_apply_stop, _h_apply_continue, _h_apply_cancel,
    _h_apply_accept, _h_apply_reject,
    _h_eval_run, _h_eval_fetch, _h_eval_cancel,
    _h_abtest_create, _h_abtest_stop, _h_abtest_continue, _h_abtest_cancel,
    _h_merge_start, _h_merge_cancel,
    _h_deploy_start, _h_deploy_continue, _h_deploy_cancel,
]:
    op = _h.__name__.replace('_h_', '', 1).replace('_', '.', 1)
    OP_HANDLERS[op] = _h

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
