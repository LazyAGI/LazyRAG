from __future__ import annotations
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from evo.runtime.fs import atomic_write_json
from evo.service.core import store as _store
from evo.service.core.ops_executor import Op, OpsExecutor
from evo.service.threads.workspace import EventLog, ThreadWorkspace
OK = {'succeeded', 'accepted'}
BAD = {'failed_permanent', 'failed_transient', 'cancelled', 'rejected'}
MAIN_FLOWS = ('dataset_gen', 'eval', 'run', 'apply', 'abtest')
class ThreadDriver:
    def __init__(self, *, jm, ops: OpsExecutor) -> None:
        self.jm = jm
        self.ops = ops
        self._threads: dict[str, threading.Thread] = {}
        self._guard = threading.Lock()
    def start(self, thread_id: str) -> dict:
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        inputs = _thread_inputs(ws)
        op = {'op': 'dataset_gen.start', 'args': {'kb_id': inputs.get('kb_id'), 'algo_id': inputs.get('algo_id') or 'general_algo', 'eval_name': inputs.get('eval_name') or f'{thread_id}_eval', **({'num_cases': inputs['num_cases']} if inputs.get('num_cases') else {})}}
        return self.run_ops_async(thread_id, [op], source='default')
    def run_ops_async(self, thread_id: str, ops: list[dict[str, Any]], *, source: str) -> dict:
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        elog = EventLog(ws.events_path)
        if not ops:
            return self.runtime(thread_id)
        self._write_runtime(ws, {'status': 'running'})
        t = threading.Thread(target=self._run_ops, args=(thread_id, ops, source), daemon=True, name=f'evo-thread-driver-{thread_id}')
        with self._guard:
            self._threads[thread_id] = t
        t.start()
        return self.runtime(thread_id)
    def pause(self, thread_id: str) -> dict:
        row = self._active_task(thread_id)
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        _emit_flow_control(ws, row, 'pause')
        if row:
            self.jm.stop(row['id'])
        self._write_runtime(ws, {'status': 'paused'})
        return self.runtime(thread_id)
    def cancel(self, thread_id: str) -> dict:
        row = self._active_task(thread_id)
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        _emit_flow_control(ws, row, 'cancel')
        if row:
            self.jm.cancel(row['id'])
        self._write_runtime(ws, {'status': 'cancelled'})
        return self.runtime(thread_id)
    def retry(self, thread_id: str) -> dict:
        row = self._latest_resumable(thread_id)
        if not row:
            raise _store.StateError('NO_RESUMABLE_TASK', f'thread {thread_id} has no paused or transient failed task')
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        _emit_flow_control(ws, row, 'resume')
        self._write_runtime(ws, {'status': 'running'})
        t = threading.Thread(target=self._resume_and_advance, args=(thread_id, row['id']), daemon=True, name=f'evo-thread-retry-{thread_id}')
        with self._guard:
            self._threads[thread_id] = t
        t.start()
        return self.runtime(thread_id)
    def runtime(self, thread_id: str) -> dict:
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        data = _read_json(_runtime_path(ws)) or {'status': 'idle'}
        data['thread_id'] = thread_id
        return data
    def _run_ops(self, thread_id: str, ops: list[dict[str, Any]], source: str) -> None:
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        elog = EventLog(ws.events_path)
        try:
            last_task = None
            for item in ops:
                task = self._execute_op(thread_id, item, source, elog, ws)
                if not task:
                    return
                if task.get('id'):
                    last_task = task
            if last_task:
                self._advance_defaults(thread_id, last_task, elog, ws)
        except Exception as exc:
            self._fail_thread(ws, elog, exc)
        finally:
            with self._guard:
                self._threads.pop(thread_id, None)
    def _resume_and_advance(self, thread_id: str, task_id: str) -> None:
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        elog = EventLog(ws.events_path)
        try:
            self.jm.cont(task_id)
            task = self._wait_task(task_id, elog, ws)
            if task and task.get('status') in OK:
                self._advance_defaults(thread_id, task, elog, ws)
        except Exception as exc:
            self._fail_thread(ws, elog, exc)
    def _execute_op(self, thread_id: str, item: dict[str, Any], source: str, elog: EventLog, ws: ThreadWorkspace, sink: object | None=None) -> dict | None:
        op_name = item['op']
        args = _with_thread_inputs(item.get('args') or {}, op_name, ws)
        for attempt in range(1, 4):
            result = self.ops.execute([Op(op_name, args)], thread_id=thread_id)[0]
            if result.error:
                if attempt < 3:
                    continue
                self._fail_thread(ws, elog, RuntimeError(str(result.error)))
                return None
            if result.status != 'submitted':
                return {}
            if not result.task_id:
                self._fail_thread(ws, elog, RuntimeError(f'{op_name} submitted no task_id'))
                return None
            task = self._wait_task(result.task_id, elog, ws)
            if task and task.get('status') in OK:
                return task
            if _task_ends_thread(task):
                return task
            if task and task.get('status') == 'paused':
                self._write_runtime(ws, {'status': 'paused', 'active_task_id': result.task_id})
                return None
            if task and task.get('status') == 'failed_transient' and (attempt < 3):
                try:
                    for retry_attempt in range(attempt + 1, 4):
                        self.jm.cont(result.task_id)
                        task = self._wait_task(result.task_id, elog, ws)
                        if task and task.get('status') in OK:
                            return task
                        if not task or task.get('status') != 'failed_transient':
                            break
                except Exception:
                    pass
                if task and task.get('status') == 'failed_transient':
                    self._fail_thread(ws, elog, RuntimeError(f"{op_name} failed with task status {task.get('status')}"))
                    return None
            if attempt == 3:
                self._fail_thread(ws, elog, RuntimeError(f"{op_name} failed with task status {(task or {}).get('status')}"))
                return None
        return None
    def _wait_task(self, task_id: str, elog: EventLog, ws: ThreadWorkspace) -> dict | None:
        self._write_runtime(ws, {'status': 'running', 'active_task_id': task_id})
        last = None
        while True:
            row = _store.get(self.jm.store, task_id)
            if not row:
                return None
            status = row.get('status')
            if status != last:
                last = status
            if status in OK or status in BAD or status == 'paused':
                return row
            time.sleep(1.0)
    def _advance_defaults(self, thread_id: str, task: dict, elog: EventLog, ws: ThreadWorkspace) -> None:
        current = task
        while True:
            op = _next_default_op(current, self.jm.store, ws)
            if _checkpoint_after(current, op, self.jm.store, ws, elog, self._write_runtime):
                return
            if not op:
                if current.get('flow') == 'abtest' and current.get('status') == 'succeeded' or _task_ends_thread(current):
                    self._write_runtime(ws, {'status': 'ended', 'active_task_id': None})
                else:
                    self._write_runtime(ws, {'status': 'idle', 'active_task_id': None})
                return
            current = self._execute_op(thread_id, op, 'default', elog, ws)
            if not current:
                return
    def _active_task(self, thread_id: str) -> dict | None:
        rows = [r for r in _thread_task_rows(self.jm.config.storage.base_dir, thread_id) if r.get('flow') in MAIN_FLOWS and r.get('status') in ('queued', 'running', 'stopping', 'paused', 'failed_transient')]
        rows.sort(key=lambda r: r.get('created_at', 0), reverse=True)
        return rows[0] if rows else None
    def _latest_resumable(self, thread_id: str) -> dict | None:
        rows = [r for r in _thread_task_rows(self.jm.config.storage.base_dir, thread_id) if r.get('flow') in MAIN_FLOWS and r.get('status') in ('paused', 'failed_transient')]
        rows.sort(key=lambda r: r.get('updated_at', 0), reverse=True)
        return rows[0] if rows else None
    def _write_runtime(self, ws: ThreadWorkspace, patch: dict) -> None:
        path = _runtime_path(ws)
        data = _read_json(path) or {}
        data.update(patch)
        data['updated_at'] = time.time()
        atomic_write_json(path, data)
    def _fail_thread(self, ws: ThreadWorkspace, elog: EventLog, exc: Exception) -> None:
        self._write_runtime(ws, {'status': 'failed', 'active_task_id': None, 'last_error': str(exc)})
def _runtime_path(ws: ThreadWorkspace) -> Path:
    return ws.dir / 'runtime.json'
def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
def _thread_task_rows(base_dir: Path, thread_id: str) -> list[dict]:
    task_dir = Path(base_dir) / 'state' / 'threads' / thread_id / 'tasks'
    rows = []
    for path in sorted(task_dir.glob('*.json')):
        row = _read_json(path)
        if row and row.get('thread_id') == thread_id:
            rows.append(row)
    return rows
def _task_ends_thread(row: dict | None) -> bool:
    if not row:
        return False
    return row.get('flow') == 'apply' and row.get('status') == 'failed_permanent' and (row.get('error_code') == 'OPENCODE_NO_CHANGES')
def _checkpoint_after(task: dict, next_op: dict | None, store: _store.FsStateStore, ws: ThreadWorkspace, elog: EventLog, write_runtime) -> bool:
    flow = task.get('flow')
    if task.get('status') not in OK or flow not in MAIN_FLOWS:
        return False
    if flow != 'abtest' and not next_op:
        return False
    existing = ws.load_checkpoint()
    if existing and existing.get('completed_task_id') == task.get('id'):
        return True
    data = _checkpoint_payload(task, next_op, store, ws)
    ws.save_checkpoint(data)
    _append_message(ws.messages_path, 'assistant', data['message'])
    elog.append_event('checkpoint.wait', task_id=task.get('id'), payload=data)
    status = 'ended' if flow == 'abtest' else 'waiting_checkpoint'
    write_runtime(ws, {'status': status, 'active_task_id': None, 'pending_checkpoint': data})
    return True
def _checkpoint_payload(task: dict, next_op: dict | None, store: _store.FsStateStore, ws: ThreadWorkspace) -> dict:
    flow = task.get('flow')
    artifacts = _checkpoint_artifacts(task, store, ws)
    return {'checkpoint_id': f"ckpt_{flow}_{uuid.uuid4().hex[:8]}", 'stage': flow, 'completed_flow': flow, 'completed_task_id': task.get('id'), 'next_op': next_op, 'allowed_stages': list(MAIN_FLOWS), 'artifacts': artifacts, 'message': _checkpoint_message(flow, artifacts, next_op), 'status': 'pending', 'created_at': time.time()}
def _checkpoint_artifacts(task: dict, store: _store.FsStateStore, ws: ThreadWorkspace) -> dict:
    payload = task.get('payload') or {}
    result = payload.get('result') or {}
    flow = task.get('flow')
    out: dict[str, object] = {'task_id': task.get('id'), 'status': task.get('status')}
    if flow == 'dataset_gen':
        out.update({'dataset_id': payload.get('eval_name') or task.get('id'), 'cases': payload.get('cases')})
    elif flow == 'eval':
        out.update({'eval_id': payload.get('eval_id') or payload.get('dataset_id'), 'dataset_id': payload.get('dataset_id'), 'cases': payload.get('cases')})
    elif flow == 'run':
        rid = payload.get('report_id')
        out.update({'report_id': rid, 'report_path': str(ws.dir / 'outputs' / 'reports' / f'{rid}.json') if rid else None})
    elif flow == 'apply':
        out.update({'apply_id': task.get('id'), 'final_commit': task.get('final_commit') or result.get('final_commit'), 'diff_index': result.get('diff_index'), 'candidate_chat_id': result.get('candidate_chat_id'), 'candidate_chat_url': result.get('candidate_chat_url'), 'candidate_status': result.get('candidate_status')})
    elif flow == 'abtest':
        abtest_id = task.get('id')
        out.update({'abtest_id': abtest_id, 'verdict': payload.get('verdict'), 'new_eval_id': payload.get('new_eval_id'), 'summary_path': str(ws.abtest_dir(abtest_id) / 'summary.json')})
    return {k: v for (k, v) in out.items() if v is not None}
def _checkpoint_message(flow: str, artifacts: dict, next_op: dict | None) -> str:
    labels = {'dataset_gen': '评测集生成', 'eval': '评测执行', 'run': '分析流程', 'apply': '代码修改和新服务部署', 'abtest': 'ABTest'}
    done = labels.get(flow, flow)
    facts = ', '.join((f'{k}={v}' for (k, v) in artifacts.items() if k not in {'status'}))
    if next_op:
        return f'{done}已完成（{facts}）。是否继续下一步：{next_op.get("op")}？你也可以说明要回退到某个阶段重新执行。'
    return f'{done}已完成（{facts}）。流程已结束，你可以查看对比报告或要求回退到某个阶段重新执行。'
def _append_message(path: Path, role: str, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'role': role, 'content': content, 'ts': time.time()}, ensure_ascii=False) + '\n')
def _emit_flow_control(ws: ThreadWorkspace, row: dict | None, event: str) -> None:
    flow = (row or {}).get('flow')
    if flow in {'dataset_gen', 'eval', 'run', 'apply'}:
        tag = f'{flow}.{event}'
    else:
        return
    EventLog(ws.events_path).append_event(tag, task_id=(row or {}).get('id'), payload={'status': (row or {}).get('status')})
def _thread_inputs(ws: ThreadWorkspace) -> dict:
    data = _read_json(ws.thread_meta_path) or {}
    return data.get('inputs') or {}
def _with_thread_inputs(args: dict, op_name: str, ws: ThreadWorkspace) -> dict:
    out = dict(args)
    inputs = _thread_inputs(ws)
    if op_name == 'eval.run' and inputs.get('target_chat_url'):
        out.setdefault('target_chat_url', inputs['target_chat_url'])
    if op_name == 'eval.run':
        dataset_name = inputs.get('dataset_name') or inputs.get('algo_id')
        if not dataset_name or str(dataset_name).startswith('ds_'):
            dataset_name = inputs.get('algo_id') or 'general_algo'
        if dataset_name:
            out.setdefault('options', {}).setdefault('dataset_name', dataset_name)
        if inputs.get('kb_id'):
            out.setdefault('options', {}).setdefault('filters', {'kb_id': inputs['kb_id']})
    return out
def _next_default_op(task: dict, store: _store.FsStateStore, ws: ThreadWorkspace) -> dict | None:
    flow = task.get('flow')
    payload = task.get('payload') or {}
    if flow == 'dataset_gen':
        dataset_id = payload.get('eval_name') or task.get('id')
        return {'op': 'eval.run', 'args': {'dataset_id': dataset_id}}
    if flow == 'eval':
        eval_id = payload.get('eval_id')
        return {'op': 'run.start', 'args': {'eval_id': eval_id}} if eval_id else None
    if flow == 'run':
        report_id = payload.get('report_id')
        return {'op': 'apply.start', 'args': {'report_id': report_id}} if report_id else None
    if flow == 'apply':
        (eval_id, dataset_id, eval_options) = _latest_eval(store, ws.thread_id)
        result = payload.get('result') or {}
        if eval_id and dataset_id and _apply_ready_for_abtest(task, store):
            args = {'apply_id': task['id'], 'baseline_eval_id': eval_id, 'dataset_id': dataset_id}
            if eval_options:
                args['eval_options'] = eval_options
            if result.get('candidate_chat_id'):
                args['candidate_chat_id'] = result['candidate_chat_id']
            return {'op': 'abtest.create', 'args': args}
    return None
def _latest_eval(store: _store.FsStateStore, thread_id: str) -> tuple[str | None, str | None, dict]:
    rows = _store.list_flow_tasks_by_thread(store, 'eval', thread_id)
    for row in reversed(rows):
        payload = row.get('payload') or {}
        dataset_id = payload.get('dataset_id')
        if row.get('status') == 'succeeded' and dataset_id:
            return (dataset_id, dataset_id, dict(payload.get('eval_options') or {}))
    return (None, None, {})
def _apply_ready_for_abtest(task: dict, store: _store.FsStateStore) -> bool:
    result = (task.get('payload') or {}).get('result') or {}
    if task.get('status') not in {'succeeded', 'accepted'}:
        return False
    if result.get('status') != 'SUCCEEDED':
        return False
    if not (task.get('final_commit') or result.get('final_commit')):
        return False
    rounds = _store.list_rounds(store, task['id'])
    return bool(rounds and rounds[-1].get('test_passed') == 1)
