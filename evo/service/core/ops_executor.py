from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from evo.orchestrator import capabilities as caps
from evo.runtime.config import EVO_TARGET_CHAT_URL
from evo.service.core import schemas, state as thread_state, store
if TYPE_CHECKING:
    from evo.service.core.manager import JobManager
log = logging.getLogger('evo.service.core.ops_executor')


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


MODELS = {
    'run.start': schemas.RunCreate,
    'apply.start': schemas.ApplyCreate,
    'dataset_gen.start': schemas.DatasetGenCreate,
    'eval.run': schemas.EvalCreate,
    'eval.fetch': schemas.EvalCreate,
    'abtest.create': schemas.AbtestCreate,
}
START = {
    'run.start': 'submit_run',
    'apply.start': 'submit_apply',
    'dataset_gen.start': 'submit_dataset_gen',
    'eval.run': 'submit_eval',
    'eval.fetch': 'submit_eval',
    'abtest.create': 'submit_abtest',
}
CONTROL = {
    'run.stop': ('stop', 'stopped'),
    'run.continue': ('cont', 'continued'),
    'run.cancel': ('cancel', 'cancelled'),
    'apply.stop': ('stop', 'stopped'),
    'apply.continue': ('cont', 'continued'),
    'apply.cancel': ('cancel', 'cancelled'),
    'apply.accept': ('accept', 'accepted'),
    'apply.reject': ('reject', 'rejected'),
    'eval.cancel': ('cancel', 'cancelled'),
    'abtest.stop': ('stop', 'stopped'),
    'abtest.continue': ('cont', 'continued'),
    'abtest.cancel': ('cancel', 'cancelled'),
    'dataset_gen.cancel': ('cancel', 'cancelled'),
}
FLOW_PRIORITY = ('run', 'apply', 'eval', 'dataset_gen', 'abtest')


class OpsExecutor:
    def __init__(self, jm: 'JobManager') -> None:
        self._jm = jm

    def execute(self, ops: list[Op], *, thread_id: str | None = None, idem_key: str | None = None) -> list[OpResult]:
        return [self._one(op, thread_id) for op in ops]

    def _one(self, op: Op, thread_id: str | None) -> OpResult:
        try:
            raw_args = {**op.args, **({'thread_id': thread_id} if thread_id else {})}
            if op.op in CONTROL and not raw_args.get('task_id'):
                raw_args['task_id'] = _control_task_id(self._jm, op.op, raw_args)
            caps.validate(op.op, raw_args)
            args = _validated_args(op.op, raw_args)
            if op.op in START:
                tid = getattr(self._jm, START[op.op])(**args)
                return OpResult(op=op.op, task_id=tid, status='submitted')
            if op.op in CONTROL:
                method, status = CONTROL[op.op]
                tid = args['task_id']
                data = getattr(self._jm, method)(tid)
                return OpResult(op=op.op, task_id=tid, status=status, data=data)
            if op.op == 'task.stop_active':
                return _active_result(self._jm, args, 'stop', 'stopped', require_running=True)
            if op.op == 'task.cancel_active':
                return _active_result(self._jm, args, 'cancel', 'cancelled')
            if op.op in {'task.continue_latest', 'thread.retry'}:
                tid = args.get('task_id') or _wait_resumable(self._jm, args)
                self._jm.cont(tid)
                return OpResult(op=op.op, task_id=tid, status='continued' if op.op.startswith('task.') else 'submitted')
            if op.op.startswith('checkpoint.'):
                return self._checkpoint(op, thread_id)
            return OpResult(
                op=op.op,
                status='unknown',
                error={
                    'code': 'UNSUPPORTED_OP',
                    'message': f'{op.op} not implemented'})
        except Exception as exc:
            log.exception('op %s failed: %s', op.op, exc)
            return OpResult(
                op=op.op,
                status='failed',
                error={
                    'code': getattr(
                        exc,
                        'code',
                        'EXEC_ERROR'),
                    'message': str(exc)})

    def _checkpoint(self, op: Op, thread_id: str | None) -> OpResult:
        if not thread_id:
            raise store.StateError('CHECKPOINT_NO_THREAD', 'checkpoint op requires thread_id')
        from evo.service.threads.workspace import EventLog, ThreadWorkspace
        ws = ThreadWorkspace(self._jm.config.storage.base_dir, thread_id)
        checkpoint = ws.load_checkpoint()
        if not checkpoint:
            raise store.StateError('CHECKPOINT_NOT_FOUND', f'thread {thread_id} has no pending checkpoint')
        elog = EventLog(ws.events_path)
        if op.op == 'checkpoint.answer':
            return OpResult(op=op.op, status='answered', data={'checkpoint_id': checkpoint.get('checkpoint_id')})
        ws.clear_checkpoint()
        elog.append_event(op.op, payload={'checkpoint_id': checkpoint.get('checkpoint_id'), **op.args})
        terminal = bool(checkpoint.get('terminal'))
        thread_state.save_thread(
            self._jm.config.storage.base_dir,
            thread_state.ThreadRecord(
                id=thread_id,
                state=thread_state.THREAD_SUCCEEDED if terminal and op.op == 'checkpoint.continue'
                else thread_state.THREAD_IDLE,
            ),
        )
        if op.op == 'checkpoint.cancel':
            return OpResult(op=op.op, status='cancelled', data={'checkpoint_id': checkpoint.get('checkpoint_id')})
        next_op = checkpoint.get('next_op') if op.op == 'checkpoint.continue' else _rewind_op(
            self._jm, thread_id, checkpoint, op.args)
        if not isinstance(next_op, dict) or not next_op.get('op'):
            return OpResult(op=op.op, status='done', data={'checkpoint_id': checkpoint.get('checkpoint_id')})
        result = self._one(Op(op=next_op['op'], args=next_op.get('args') or {}), thread_id)
        return OpResult(op=op.op, task_id=result.task_id, status=result.status, error=result.error, data=result.data)


def _validated_args(op: str, args: dict[str, Any]) -> dict[str, Any]:
    model = MODELS.get(op)
    return model(**args).model_dump(exclude_none=True) if model else args


def _active_result(jm: 'JobManager', args: dict[str, Any], method: str,
                   status: str, *, require_running: bool = False) -> OpResult:
    tid = _active_task(jm, args, require_running=require_running)
    return OpResult(op=f'task.{method}_active', task_id=tid, status=status, data=getattr(jm, method)(tid))


def _active_task(jm: 'JobManager', args: dict[str, Any], *, require_running: bool = False) -> str:
    for flow in ((args.get('flow'),) if args.get('flow') else FLOW_PRIORITY):
        rows = store.list_active(jm.store, flow, scope='thread' if args.get(
            'thread_id') else 'global', thread_id=args.get('thread_id'))
        rows = [r for r in rows if (r.get('status') == 'running' if require_running else True)]
        if rows:
            rows.sort(key=lambda r: (r.get('status') != 'running', -float(r.get('created_at') or 0)))
            return rows[0]['id']
    raise store.StateError('NO_ACTIVE_TASK', f"no active task found for flow={args.get('flow')!r}")


def _control_task_id(jm: 'JobManager', op: str, args: dict[str, Any]) -> str:
    flow, action = op.split('.', 1)
    if action == 'continue':
        return _wait_resumable(jm, {'flow': flow, 'thread_id': args.get('thread_id')})
    if action in {'stop', 'cancel'}:
        return _active_task(jm, {'flow': flow, 'thread_id': args.get('thread_id')}, require_running=action == 'stop')
    rows = store.list_flow_tasks_by_thread(jm.store, flow, args['thread_id']) if args.get(
        'thread_id') else store.list_recent(jm.store, flow, 100)
    rows.sort(key=lambda row: float(row.get('updated_at') or 0), reverse=True)
    if rows:
        return rows[0]['id']
    raise store.StateError('TASK_NOT_FOUND', f'no task found for flow={flow!r}')


def _wait_resumable(jm: 'JobManager', args: dict[str, Any]) -> str:
    deadline = time.time() + 15
    while time.time() < deadline:
        candidates: list[dict[str, Any]] = []
        for flow in ((args.get('flow'),) if args.get('flow') else FLOW_PRIORITY):
            rows = store.list_flow_tasks_by_thread(jm.store, flow, args['thread_id']) if args.get(
                'thread_id') else store.list_recent(jm.store, flow, 100)
            latest_success_at = max(
                (float(r.get('updated_at') or 0) for r in rows if r.get('status') == 'succeeded'),
                default=0.0,
            )
            candidates.extend(
                r for r in rows
                if r.get('status') in {'paused', 'failed_transient'}
                and float(r.get('updated_at') or 0) > latest_success_at
            )
        if candidates:
            candidates.sort(key=lambda r: r.get('updated_at', 0), reverse=True)
            return candidates[0]['id']
        time.sleep(0.2)
    raise store.StateError('NO_RESUMABLE_TASK',
                           f"no paused or transient failed task found for flow={args.get('flow')!r}")


def _rewind_op(jm: 'JobManager', thread_id: str, checkpoint: dict, args: dict[str, Any]) -> dict | None:
    from evo.service.threads.workspace import ThreadWorkspace
    stage = args.get('to_stage')
    patch = args.get('input_patch') or {}
    ws = ThreadWorkspace(jm.config.storage.base_dir, thread_id)
    inputs = (thread_state.read_json(ws.thread_meta_path) or {}).get('inputs') or {}
    if stage == 'dataset_gen':
        num_cases = patch.get('num_cases') or inputs.get('num_cases')
        return {
            'op': 'dataset_gen.start',
            'args': {
                'kb_id': patch.get('kb_id') or inputs.get('kb_id'),
                'algo_id': patch.get('algo_id') or inputs.get('algo_id') or 'general_algo',
                'eval_name': patch.get('eval_name') or inputs.get('eval_name') or f'{thread_id}_eval',
                **({'num_cases': num_cases} if num_cases else {}),
            },
        }
    if stage == 'eval':
        dataset_id = _latest_artifact(ws, 'dataset_ids')
        if not dataset_id:
            return None
        args: dict[str, Any] = {'dataset_id': dataset_id, 'target_chat_url': EVO_TARGET_CHAT_URL}
        if inputs.get('dataset_name'):
            args['options'] = {'dataset_name': inputs['dataset_name']}
        return {'op': 'eval.run', 'args': args}
    if stage == 'run':
        eval_id = _latest_artifact(ws, 'eval_ids')
        return {'op': 'run.start', 'args': {'eval_id': eval_id, **_extra(patch)}} if eval_id else None
    if stage == 'apply':
        report_id = _latest_run_report(jm, thread_id)
        return {'op': 'apply.start', 'args': {'report_id': report_id, **_extra(patch)}} if report_id else None
    if stage == 'abtest':
        prev = _latest_task(jm, 'abtest', thread_id)
        prev_payload = (prev or {}).get('payload') or {}
        apply_id = patch.get('apply_id') or prev_payload.get('apply_id') or _latest_artifact(ws, 'apply_ids')
        baseline_eval_id = patch.get('baseline_eval_id') or prev_payload.get('baseline_eval_id')
        dataset_id = patch.get('dataset_id') or prev_payload.get('dataset_id') or _latest_artifact(ws, 'dataset_ids')
        if not (apply_id and baseline_eval_id and dataset_id):
            return None
        inputs = (thread_state.read_json(ws.thread_meta_path) or {}).get('inputs') or {}
        op_args = {
            'apply_id': apply_id,
            'baseline_eval_id': baseline_eval_id,
            'dataset_id': dataset_id,
            'target_chat_url': EVO_TARGET_CHAT_URL,
        }
        if inputs.get('dataset_name'):
            op_args['eval_options'] = {'dataset_name': inputs['dataset_name']}
        return {'op': 'abtest.create', 'args': op_args}
    return checkpoint.get('next_op')


def _latest_artifact(ws: Any, kind: str) -> str | None:
    vals = ws.load_artifacts().get(kind) or []
    return vals[-1] if vals else None


def _latest_run_report(jm: 'JobManager', thread_id: str) -> str | None:
    rows = store.list_flow_tasks_by_thread(jm.store, 'run', thread_id)
    rows.sort(key=lambda row: row.get('updated_at') or 0, reverse=True)
    for row in rows:
        if row.get('status') == 'succeeded':
            return (row.get('payload') or {}).get('report_id') or row.get('report_id')
    return None


def _latest_task(jm: 'JobManager', flow: str, thread_id: str) -> dict | None:
    rows = store.list_flow_tasks_by_thread(jm.store, flow, thread_id)
    rows.sort(key=lambda row: row.get('updated_at') or 0, reverse=True)
    return rows[0] if rows else None


def _extra(patch: dict[str, Any]) -> dict[str, Any]:
    return {'extra_instructions': patch['extra_instructions']} if patch.get('extra_instructions') else {}
