from __future__ import annotations
import json
import asyncio
import logging
import queue
import threading
import time
import uuid
from typing import TYPE_CHECKING, Callable
from fastapi import APIRouter, Body, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse
from evo.service.core import schemas as api_schemas
from evo.service.core import store as _store
from evo.service.core.intent_store import IntentStore
from evo.service.core.ops_executor import OpsExecutor, Op
from evo.service.threads.driver import ThreadDriver
from evo.orchestrator.planner import Planner, PlanContext
from evo.orchestrator import capabilities as caps

if TYPE_CHECKING:
    from evo.service.core.manager import JobManager
    from evo.service.threads.workspace import EventLog

log = logging.getLogger('evo.service.threads.hub')


class ThreadHub:
    def __init__(self, *, jm: 'JobManager', planner: Planner, intent_store: IntentStore, ops: OpsExecutor) -> None:
        self.jm = jm
        self.planner = planner
        self.intents = intent_store
        self.ops = ops
        self.driver = ThreadDriver(jm=jm, ops=ops)
        self._auto_threads: dict[str, threading.Event] = {}
        self._message_cancels: dict[str, threading.Event] = {}
        self._message_lock = threading.Lock()

    def list_threads(self) -> list[dict]:
        base = self.intents._base_dir.parent / 'threads'
        if not base.exists():
            return []
        return [__import__('json').loads(p.read_text(encoding='utf-8')) for p in sorted(base.glob('*/thread.json'))]

    def list_thread_statuses(self) -> dict:
        threads = []
        counts: dict[str, int] = {}
        for meta in self.list_threads():
            thread_id = str(meta.get('id') or '')
            if not thread_id:
                continue
            status = self.flow_status(thread_id)
            item = {
                **status,
                'title': meta.get('title') or '',
                'mode': meta.get('mode') or 'interactive',
                'created_at': meta.get('created_at'),
                'updated_at': meta.get('updated_at'),
            }
            threads.append(item)
            counts[item['status']] = counts.get(item['status'], 0) + 1
        threads.sort(key=lambda row: row.get('updated_at') or row.get('created_at') or 0.0, reverse=True)
        return {'total': len(threads), 'counts': counts, 'threads': threads}

    def create_thread(self, payload: dict) -> dict:
        mode = payload.get('mode', 'interactive')
        if mode not in ('auto', 'interactive'):
            raise HTTPException(400, f'bad mode {mode!r}')
        import uuid
        import time

        tid = f'thr-{uuid.uuid4().hex[:8]}'
        from evo.service.threads.workspace import ThreadWorkspace

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, tid)
        meta = {
            'id': tid,
            'mode': mode,
            'title': payload.get('title', ''),
            'inputs': payload.get('inputs') or {},
            'status': 'active',
            'created_at': time.time(),
            'updated_at': time.time(),
        }
        from evo.runtime.fs import atomic_write_json

        atomic_write_json(ws.thread_meta_path, meta)
        if mode == 'auto' and payload.get('start_auto', True):
            self.start(tid)
            self.auto_start(tid)
        return meta

    def get_thread(self, thread_id: str) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = __import__('json').loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        meta['artifacts'] = ws.load_artifacts()
        meta['pending_intents'] = self.intents.list_pending(thread_id)
        meta['pending_checkpoints'] = [ws.load_checkpoint()] if ws.load_checkpoint() else []
        return meta

    def flow_status(self, thread_id: str) -> dict:
        thread_dir = self.jm.config.storage.base_dir / 'state' / 'threads' / thread_id
        if not (thread_dir / 'thread.json').exists():
            return {'thread_id': thread_id, 'status': 'not_found'}
        from evo.service.threads.workspace import ThreadWorkspace

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
        rows = _thread_task_rows(self.jm, thread_id, ws.load_artifacts())
        active_tasks = [r for r in rows if _task_is_executing(r)]
        runtime = _thread_runtime(ws)
        latest_abtest = _latest_flow(rows, 'abtest')
        latest_apply = _latest_flow(rows, 'apply')
        checkpoint = ws.load_checkpoint()
        report_ready = _abtest_report_ready(ws, latest_abtest)
        ended = _thread_has_ended(rows, active_tasks, latest_abtest, latest_apply, report_ready)
        status = _flow_status(runtime, rows, active_tasks, checkpoint, ended)
        return {
            'thread_id': thread_id,
            'status': status,
            'active_task_ids': [r['id'] for r in active_tasks],
            'latest_abtest_id': latest_abtest.get('id') if latest_abtest else None,
            'latest_abtest_status': latest_abtest.get('status') if latest_abtest else None,
            'report_ready': report_ready,
            'pending_checkpoint': checkpoint,
        }

    def post_message(self, thread_id: str, content: str) -> dict:
        from evo.service.threads.workspace import EventLog, ThreadWorkspace

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        elog = EventLog(ws.events_path)
        _append_message(ws.messages_path, 'user', content)
        elog.append_event('message.user', payload={'content': content})
        ctx = self._plan_context(thread_id, ws)
        intent = self.planner.draft(content, ctx)
        self.intents.save(intent)
        plan = self.planner.materialize(intent, ctx)
        _append_message(ws.messages_path, 'assistant', intent.reply)
        draft_trace = intent.trace or {}
        planned_ops = [{'op': op.get('op'), 'args': op.get('args', {})} for op in plan.ops]
        elog.append_event(
            'intent.thought',
            payload={
                'intent_id': intent.intent_id,
                'decision_summary': intent.thinking or _intent_summary(intent, plan),
                'identified_intent': [p.op for p in intent.suggested_ops_preview],
                'planned_ops': planned_ops,
                'source': draft_trace.get('source'),
                'warnings': plan.warnings,
            },
        )
        elog.append_event('message.assistant', payload={'content': intent.reply})
        elog.append_event(
            'intent.reply', payload={'intent_id': intent.intent_id, 'content': intent.reply, 'planned_ops': planned_ops}
        )
        self.intents.transition(intent.intent_id, 'confirm')
        self.intents.transition(intent.intent_id, 'materialize')
        if _is_checkpoint_plan(plan.ops):
            self._execute_checkpoint_plan(thread_id, ws, elog, plan.ops[0])
        else:
            self.driver.run_ops_async(thread_id, plan.ops, source='user')
        return {
            'intent_id': intent.intent_id,
            'reply': intent.reply,
            'thinking': intent.thinking,
            'requires_confirm': False,
            'preview': [
                {'op': p.op, 'humanized': p.humanized, 'safety': p.safety, 'params_summary': p.params_summary}
                for p in intent.suggested_ops_preview
            ],
            'warnings': plan.warnings,
        }

    async def post_message_stream(self, thread_id: str, content: str):
        message_id = f'msg_{thread_id}_{uuid.uuid4().hex[:8]}'
        cancel = threading.Event()
        async for event in self._stream_message_with_cancel(thread_id, content, message_id, cancel):
            yield event

    async def _stream_message_with_cancel(
        self, thread_id: str, content: str, message_id: str, cancel: threading.Event
    ):
        self._register_message_cancel(thread_id, message_id, cancel)
        yield _sse('intent_start', {'thread_id': thread_id, 'message_id': message_id})
        yield _sse('thinking_delta', {'delta': '正在理解你的请求并规划下一步。', 'message_id': message_id})
        try:
            async for event in self._post_message_stream_events(thread_id, content, message_id, cancel):
                yield event
        except asyncio.CancelledError:
            cancel.set()
            raise
        finally:
            self._clear_message_cancel(thread_id, message_id)

    async def auto_start_stream(self, thread_id: str, interval_s: float = 5.0):
        from evo.service.threads.workspace import ThreadWorkspace

        if thread_id in self._auto_threads and (not self._auto_threads[thread_id].is_set()):
            yield _sse('error', {'code': 'AUTO_ALREADY_RUNNING', 'message': 'auto loop is already running'})
            return
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
        if not ws.thread_meta_path.exists():
            yield _sse('error', {'code': 404, 'message': f'thread {thread_id} not found'})
            return
        meta = json.loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        if meta.get('mode') != 'auto':
            yield _sse('error', {'code': 400, 'message': 'auto_start requires thread mode auto'})
            return
        stop = threading.Event()
        self._auto_threads[thread_id] = stop
        client_cancelled = False
        yield _sse('auto_start', {'thread_id': thread_id, 'interval_s': interval_s})
        try:
            while not stop.is_set():
                ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
                message = _auto_message(self.jm, thread_id, ws)
                if not message:
                    yield _sse('auto_wait', {'thread_id': thread_id})
                    await asyncio.to_thread(stop.wait, interval_s)
                    continue
                yield _sse('auto_message', {'thread_id': thread_id, 'content': message})
                message_id = f'msg_{thread_id}_{uuid.uuid4().hex[:8]}'
                cancel = threading.Event()
                linker = asyncio.create_task(_cancel_when_stopped(stop, cancel))
                try:
                    async for event in self._stream_message_with_cancel(thread_id, message, message_id, cancel):
                        yield event
                finally:
                    linker.cancel()
                await asyncio.to_thread(stop.wait, interval_s)
        except asyncio.CancelledError:
            client_cancelled = True
            stop.set()
            raise
        finally:
            stop.set()
            if self._auto_threads.get(thread_id) is stop:
                self._auto_threads.pop(thread_id, None)
        if not client_cancelled:
            yield _sse('auto_stop', {'thread_id': thread_id})

    async def _post_message_stream_events(
        self, thread_id: str, content: str, message_id: str, cancel: threading.Event
    ):
        deltas: queue.Queue[str | None] = queue.Queue()
        try:
            task = asyncio.create_task(
                asyncio.to_thread(self._post_message_stream_result, thread_id, content, cancel, deltas.put)
            )
            task.add_done_callback(_consume_task_exception)
            while not task.done():
                if cancel.is_set():
                    yield _sse(
                        'error',
                        {'code': 'MESSAGE_CANCELLED', 'message': 'message generation cancelled', 'message_id': message_id},  # noqa: E501
                    )
                    return
                try:
                    delta = await asyncio.to_thread(deltas.get, True, 0.1)
                except queue.Empty:
                    continue
                if delta:
                    yield _sse('answer_delta', {'delta': delta, 'message_id': message_id})
                    await asyncio.sleep(0)
            while not deltas.empty():
                delta = deltas.get_nowait()
                if delta:
                    yield _sse('answer_delta', {'delta': delta, 'message_id': message_id})
                    await asyncio.sleep(0)
            result = await task
        except HTTPException as exc:
            yield _sse('error', {'code': exc.status_code, 'message': str(exc.detail), 'message_id': message_id})
            return
        except Exception as exc:
            code = 'MESSAGE_CANCELLED' if cancel.is_set() or str(exc) == 'MESSAGE_CANCELLED' else 'MESSAGE_FAILED'
            yield _sse('error', {'code': code, 'message': str(exc), 'message_id': message_id})
            return
        actions = [
            {
                'op': item.get('op'),
                'args': item.get('params_summary') or {},
                'humanized': item.get('humanized'),
                'safety': item.get('safety'),
            }
            for item in (result.get('preview') or [])
        ]
        yield _sse(
            'plan_ready',
            {
                'message_id': message_id,
                'intent_id': result.get('intent_id'),
                'actions': actions,
                'warnings': result.get('warnings') or [],
            },
        )
        for item in actions:
            yield _sse(
                'action',
                {
                    'message_id': message_id,
                    'intent_id': result.get('intent_id'),
                    'op': item.get('op'),
                    'args': item.get('args') or {},
                    'humanized': item.get('humanized'),
                    'safety': item.get('safety'),
                },
            )
            await asyncio.sleep(0)
        yield _sse(
            'done',
            {
                'message_id': message_id,
                'intent_id': result.get('intent_id'),
                'status': 'ok',
                'requires_confirm': result.get('requires_confirm', False),
                'warnings': result.get('warnings') or [],
                'action_count': len(actions),
            },
        )

    def _post_message_stream_result(
        self, thread_id: str, content: str, cancel: threading.Event, on_reply_delta: Callable[[str], None]
    ) -> dict:
        from evo.service.threads.workspace import EventLog, ThreadWorkspace

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        elog = EventLog(ws.events_path)
        _append_message(ws.messages_path, 'user', content)
        elog.append_event('message.user', payload={'content': content})
        ctx = self._plan_context(thread_id, ws)
        intent = None
        for event in self.planner.draft_stream(content, ctx, cancel.is_set):
            if cancel.is_set():
                raise RuntimeError('MESSAGE_CANCELLED')
            if event.get('type') == 'reply_delta':
                on_reply_delta(str(event.get('delta') or ''))
                continue
            if event.get('type') == 'final':
                intent = event['intent']
        if intent is None:
            raise RuntimeError('planner did not produce an intent')
        self.intents.save(intent)
        plan = self.planner.materialize(intent, ctx)
        _append_message(ws.messages_path, 'assistant', intent.reply)
        draft_trace = intent.trace or {}
        planned_ops = [{'op': op.get('op'), 'args': op.get('args', {})} for op in plan.ops]
        elog.append_event(
            'intent.thought',
            payload={
                'intent_id': intent.intent_id,
                'decision_summary': intent.thinking or _intent_summary(intent, plan),
                'identified_intent': [p.op for p in intent.suggested_ops_preview],
                'planned_ops': planned_ops,
                'source': draft_trace.get('source'),
                'warnings': plan.warnings,
            },
        )
        elog.append_event('message.assistant', payload={'content': intent.reply})
        elog.append_event(
            'intent.reply', payload={'intent_id': intent.intent_id, 'content': intent.reply, 'planned_ops': planned_ops}
        )
        if not intent.requires_confirm:
            self.intents.transition(intent.intent_id, 'confirm')
            self.intents.transition(intent.intent_id, 'materialize')
            if _is_checkpoint_plan(plan.ops):
                self._execute_checkpoint_plan(thread_id, ws, elog, plan.ops[0])
            else:
                self.driver.run_ops_async(thread_id, plan.ops, source='user')
        return {
            'intent_id': intent.intent_id,
            'reply': intent.reply,
            'thinking': intent.thinking,
            'requires_confirm': False,
            'preview': [
                {'op': p.op, 'humanized': p.humanized, 'safety': p.safety, 'params_summary': p.params_summary}
                for p in intent.suggested_ops_preview
            ],
            'warnings': plan.warnings,
        }

    def _execute_checkpoint_plan(self, thread_id: str, ws, elog: EventLog, op: dict) -> None:
        name = op.get('op')
        args = op.get('args') or {}
        checkpoint = ws.load_checkpoint()
        if not checkpoint:
            return
        if name == 'checkpoint.answer':
            elog.append_event(
                'checkpoint.answer',
                payload={'checkpoint_id': checkpoint.get('checkpoint_id'), 'message': args.get('message')},
            )
            return
        if name == 'checkpoint.cancel':
            ws.clear_checkpoint()
            elog.append_event(
                'checkpoint.cancel',
                payload={'checkpoint_id': checkpoint.get('checkpoint_id'), 'reason': args.get('reason')},
            )
            runtime_status = _checkpoint_cancel_runtime_status(checkpoint, _thread_runtime(ws))
            self.driver._write_runtime(ws, {'status': runtime_status, 'active_task_id': None, 'pending_checkpoint': None})  # noqa: E501
            return
        if name == 'checkpoint.continue':
            next_op = checkpoint.get('next_op')
            if not next_op:
                return
            ws.clear_checkpoint()
            elog.append_event(
                'checkpoint.continue',
                payload={
                    'checkpoint_id': checkpoint.get('checkpoint_id'),
                    'next_op': next_op,
                    'reason': args.get('reason'),
                },
            )
            self.driver._write_runtime(ws, {'status': 'running', 'active_task_id': None, 'pending_checkpoint': None})
            self.driver.run_ops_async(thread_id, [next_op], source='checkpoint')
            return
        if name == 'checkpoint.rewind':
            op_to_run = _rewind_op(self.jm, ws, args)
            ws.clear_checkpoint()
            elog.append_event(
                'checkpoint.rewind',
                payload={
                    'checkpoint_id': checkpoint.get('checkpoint_id'),
                    'to_stage': args.get('to_stage'),
                    'input_patch': args.get('input_patch') or {},
                    'op': op_to_run,
                    'reason': args.get('reason'),
                },
            )
            for row in _active_rows(self.jm, thread_id):
                try:
                    self.jm.cancel(row['id'])
                except Exception:
                    pass
            self.driver._write_runtime(ws, {'status': 'running', 'active_task_id': None, 'pending_checkpoint': None})
            self.driver.run_ops_async(thread_id, [op_to_run], source='checkpoint')

    def start(self, thread_id: str) -> dict:
        return self.driver.start(thread_id)

    def pause(self, thread_id: str) -> dict:
        return self.driver.pause(thread_id)

    def cancel(self, thread_id: str) -> dict:
        return self.driver.cancel(thread_id)

    def retry(self, thread_id: str) -> dict:
        return self.driver.retry(thread_id)

    def confirm_intent(self, thread_id: str, intent_id: str, user_edit: dict | None = None) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace, EventLog

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        EventLog(ws.events_path)
        intent_data = self.intents.get(intent_id)
        if intent_data is None:
            raise HTTPException(404, f'intent {intent_id} not found')
        if intent_data.get('thread_id') != thread_id:
            raise HTTPException(403, 'intent does not belong to this thread')
        self.intents.transition(intent_id, 'confirm')
        ctx = self._plan_context(thread_id, ws)
        from evo.service.core.intent_store import Intent, IntentPreview

        intent = Intent(
            intent_id=intent_data['intent_id'],
            thread_id=intent_data['thread_id'],
            user_message=intent_data['user_message'],
            reply=intent_data['reply'],
            suggested_ops_preview=[IntentPreview(**p) for p in intent_data.get('suggested_ops_preview', [])],
            requires_confirm=intent_data['requires_confirm'],
            thinking=intent_data.get('thinking', ''),
            created_at=intent_data['created_at'],
        )
        plan = self.planner.materialize(intent, ctx, user_edit=user_edit)
        if not plan.ops:
            raise HTTPException(400, {'code': 'PLAN_EMPTY', 'warnings': plan.warnings})
        ops = [Op(op=o['op'], args=o.get('args', {})) for o in plan.ops]
        results = self.ops.execute(ops, thread_id=intent.thread_id)
        self.intents.transition(intent_id, 'materialize')
        return {
            'intent_id': intent_id,
            'ops_executed': len(results),
            'warnings': plan.warnings,
            'results': [
                {'op': r.op, 'status': r.status, 'task_id': r.task_id, 'error': r.error, 'data': r.data}
                for r in results
            ],
        }

    def auto_step(self, thread_id: str) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id, create=False)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = __import__('json').loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        if meta.get('mode') != 'auto':
            raise HTTPException(400, 'auto_step requires thread mode auto')
        message = _auto_message(self.jm, thread_id, ws)
        if not message:
            return {'status': 'waiting', 'message': None}
        draft = self.post_message(thread_id, message)
        return {'status': 'sent', 'message': message, 'draft': draft}

    def auto_start(self, thread_id: str, interval_s: float = 5.0) -> dict:
        if thread_id in self._auto_threads and (not self._auto_threads[thread_id].is_set()):
            return {'status': 'running'}
        stop = threading.Event()
        self._auto_threads[thread_id] = stop

        def _loop() -> None:
            while not stop.is_set():
                try:
                    self.auto_step(thread_id)
                except Exception as exc:
                    log.warning('auto_step failed for %s: %s', thread_id, exc)
                stop.wait(interval_s)

        threading.Thread(target=_loop, name=f'evo-auto-{thread_id}', daemon=True).start()
        return {'status': 'started'}

    def auto_stop(self, thread_id: str) -> dict:
        ev = self._auto_threads.get(thread_id)
        if ev:
            ev.set()
        return {'status': 'stopped'}

    def cancel_intent(self, thread_id: str, intent_id: str) -> dict:
        intent_data = self.intents.get(intent_id)
        if intent_data and intent_data.get('thread_id') != thread_id:
            raise HTTPException(403, 'intent does not belong to this thread')
        row = self.intents.transition(intent_id, 'cancel')
        from evo.service.threads.workspace import ThreadWorkspace, EventLog

        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        EventLog(ws.events_path).append('intent', 'intent.cancelled', {'intent_id': intent_id})
        return row

    def cancel_message(self, thread_id: str, message_id: str | None = None) -> dict:
        key_prefix = f'{thread_id}:'
        with self._message_lock:
            if message_id:
                key = f'{thread_id}:{message_id}'
                ev = self._message_cancels.get(key)
                if ev is None:
                    raise HTTPException(404, f'message generation {message_id} not found')
                ev.set()
                return {'status': 'cancel_requested', 'thread_id': thread_id, 'message_id': message_id}
            matches = [(key, ev) for key, ev in self._message_cancels.items() if key.startswith(key_prefix)]
            for _, ev in matches:
                ev.set()
            return {'status': 'cancel_requested', 'thread_id': thread_id, 'count': len(matches)}

    def _register_message_cancel(self, thread_id: str, message_id: str, ev: threading.Event) -> None:
        with self._message_lock:
            self._message_cancels[f'{thread_id}:{message_id}'] = ev

    def _clear_message_cancel(self, thread_id: str, message_id: str) -> None:
        with self._message_lock:
            self._message_cancels.pop(f'{thread_id}:{message_id}', None)

    def _plan_context(self, thread_id: str, ws) -> PlanContext:
        snapshot = _thread_state_snapshot(self.jm, thread_id, ws.load_artifacts())
        return PlanContext(
            thread_id=thread_id,
            recent_history=_read_recent_messages(ws.messages_path, limit=20),
            thread_state_summary=_thread_state_summary(snapshot),
            capabilities_with_safety=[
                {'op': op, 'safety': caps.get(op).safety, 'flow': caps.get(op).flow} for op in caps.all_ops()
            ],
            thread_state=snapshot,
        )


def _format_artifacts(artifacts: dict) -> str:
    parts: list[str] = []
    for kind in ('dataset_ids', 'eval_ids', 'run_ids', 'apply_ids', 'apply_commit_ids', 'abtest_ids', 'chat_ids'):
        vals = artifacts.get(kind) or []
        if vals:
            parts.append(f"{kind}: {', '.join(vals[-3:])}")
    return '\n'.join(parts) if parts else ''


def _thread_state_summary(snapshot: dict) -> str:
    parts = [_format_artifacts(snapshot.get('artifacts') or {})]
    inputs = snapshot.get('inputs') or {}
    if inputs:
        parts.append('thread_inputs: ' + json.dumps(inputs, ensure_ascii=False)[:2000])
    latest = snapshot.get('latest_tasks') or {}
    if latest:
        parts.append(
            'latest_tasks: '
            + json.dumps(
                {
                    k: {'id': v.get('id'), 'status': v.get('status'), 'payload': v.get('payload')}
                    for (k, v) in latest.items()
                },
                ensure_ascii=False,
            )[:4000]
        )
    active = snapshot.get('active_tasks') or []
    if active:
        parts.append('active_tasks: ' + ', '.join((f"{r['flow']}:{r['id']}:{r['status']}" for r in active[-10:])))
    reports = []
    for rid in ((snapshot.get('artifacts') or {}).get('run_ids') or [])[-3:]:
        row = latest.get('run') if (latest.get('run') or {}).get('id') == rid else None
        if row and (row.get('payload') or {}).get('report_id'):
            reports.append((row.get('payload') or {}).get('report_id'))
    if reports:
        parts.append('latest_reports: ' + ', '.join(reports))
    return '\n'.join((p for p in parts if p))


def _thread_state_snapshot(jm, thread_id: str, artifacts: dict) -> dict:
    latest: dict[str, dict] = {}
    active = []
    rows_by_flow: dict[str, list[dict]] = {flow: [] for flow in _store.FLOWS}
    for path in jm.conn._all_task_files():
        try:
            rec = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        flow = rec.get('flow')
        if flow not in rows_by_flow or rec.get('thread_id') != thread_id:
            continue
        rows_by_flow[flow].append(rec)
        if _task_is_executing(rec):
            active.append(rec)
    for flow, rows in rows_by_flow.items():
        if rows:
            rows.sort(key=lambda r: r.get('created_at', 0.0))
            latest[flow] = rows[-1]
    from evo.service.threads.workspace import ThreadWorkspace

    ws = ThreadWorkspace(jm.config.storage.base_dir, thread_id, create=False)
    checkpoint = ws.load_checkpoint()
    return {
        'inputs': _thread_inputs(ws),
        'artifacts': artifacts,
        'active_tasks': active,
        'latest_tasks': latest,
        'pending_checkpoint': checkpoint,
        'pending_checkpoints': [checkpoint] if checkpoint else [],
    }


def _thread_task_rows(jm, thread_id: str, artifacts: dict) -> list[dict]:
    thread_dir = jm.config.storage.base_dir / 'state' / 'threads' / thread_id
    rows = []
    seen = set()
    for path in sorted((thread_dir / 'tasks').glob('*.json')):
        try:
            row = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if row.get('thread_id') == thread_id:
            rows.append(row)
            seen.add(row.get('id'))
    for kind in ('run_ids', 'apply_ids', 'abtest_ids'):
        for task_id in artifacts.get(kind) or []:
            if task_id in seen:
                continue
            row = _store.get(jm.store, task_id)
            if row and row.get('thread_id') == thread_id:
                rows.append(row)
                seen.add(task_id)
    rows.sort(key=lambda r: r.get('created_at', 0.0))
    return rows


def _latest_flow(rows: list[dict], flow: str) -> dict | None:
    for row in reversed(rows):
        if row.get('flow') == flow:
            return row
    return None


def _task_is_executing(row: dict) -> bool:
    return row.get('status') in {'queued', 'running', 'stopping', 'paused', 'failed_transient'}


def _thread_runtime(ws) -> dict:
    try:
        return json.loads((ws.dir / 'runtime.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def _thread_has_ended(
    rows: list[dict],
    active_tasks: list[dict],
    latest_abtest: dict | None,
    latest_apply: dict | None,
    report_ready: bool,
) -> bool:
    if active_tasks:
        return False
    if (
        latest_abtest
        and latest_abtest.get('status') == 'succeeded'
        and report_ready
        and _is_latest_flow_task(latest_abtest, rows)
    ):
        return True
    return bool(_task_ends_thread(latest_apply) and _is_latest_flow_task(latest_apply, rows))


def _is_latest_flow_task(row: dict | None, rows: list[dict]) -> bool:
    if not row:
        return False
    row_created = float(row.get('created_at') or 0.0)
    row_id = row.get('id')
    for other in rows:
        if other.get('id') == row_id:
            continue
        if other.get('flow') not in _store.FLOWS:
            continue
        if float(other.get('created_at') or 0.0) > row_created:
            return False
    return True


def _checkpoint_cancel_runtime_status(checkpoint: dict, runtime: dict) -> str:
    if runtime.get('status') == 'ended' or _is_terminal_checkpoint(checkpoint):
        return 'ended'
    return 'idle'


def _is_terminal_checkpoint(checkpoint: dict | None) -> bool:
    return bool(checkpoint and checkpoint.get('stage') == 'abtest' and not checkpoint.get('next_op'))


def _flow_status(
    runtime: dict, rows: list[dict], active_tasks: list[dict], checkpoint: dict | None, ended: bool
) -> str:
    runtime_status = runtime.get('status')
    if runtime_status in {'failed', 'cancelled', 'paused'}:
        return str(runtime_status)
    if active_tasks:
        return 'running'
    if _is_terminal_checkpoint(checkpoint):
        return 'ended'
    if checkpoint:
        return 'waiting_checkpoint'
    if not rows:
        return 'running' if runtime_status == 'running' else 'idle'
    if terminal_status := _latest_terminal_status(rows):
        return terminal_status
    if ended:
        return 'ended'
    if runtime_status in {'ended', 'idle'}:
        return str(runtime_status)
    if runtime_status == 'running':
        return 'running'
    return 'idle'


def _latest_terminal_status(rows: list[dict]) -> str | None:
    for row in reversed(rows):
        status = row.get('status')
        if status in {'failed_permanent', 'rejected'}:
            return 'failed'
        if status == 'cancelled':
            return 'cancelled'
        if status in {'succeeded', 'accepted'}:
            return None
    return None


def _task_ends_thread(row: dict | None) -> bool:
    if not row:
        return False
    return (
        row.get('flow') == 'apply'
        and row.get('status') == 'failed_permanent'
        and (row.get('error_code') == 'OPENCODE_NO_CHANGES')
    )


def _is_checkpoint_plan(ops: list[dict]) -> bool:
    return len(ops) == 1 and str(ops[0].get('op', '')).startswith('checkpoint.')


def _active_rows(jm, thread_id: str) -> list[dict]:
    rows = []
    for flow in _store.FLOWS:
        rows.extend(_store.list_active(jm.store, flow, scope='thread', thread_id=thread_id))
    return rows


def _rewind_op(jm, ws, args: dict) -> dict:
    stage = args['to_stage']
    patch = args.get('input_patch') or {}
    if patch:
        _patch_thread_inputs(ws, patch)
    if stage == 'dataset_gen':
        inputs = _thread_inputs(ws)
        eval_name = patch.get('eval_name') or _regen_name(inputs.get('eval_name') or ws.thread_id)
        out = {
            'op': 'dataset_gen.start',
            'args': {
                'kb_id': inputs.get('kb_id'),
                'algo_id': inputs.get('algo_id') or 'general_algo',
                'eval_name': eval_name,
            },
        }
        if inputs.get('num_cases'):
            out['args']['num_cases'] = inputs['num_cases']
        return out
    if stage == 'eval':
        dataset_id = patch.get('dataset_id') or _latest_artifact(ws, 'dataset_ids')
        if not dataset_id:
            raise HTTPException(400, 'no dataset_id available for eval rewind')
        return {'op': 'eval.run', 'args': {'dataset_id': dataset_id}}
    if stage == 'run':
        eval_id = patch.get('eval_id') or _latest_eval_id(jm, ws.thread_id)
        if not eval_id:
            raise HTTPException(400, 'no eval_id available for run rewind')
        args_out = {'eval_id': eval_id}
        if patch.get('extra_instructions'):
            args_out['extra_instructions'] = patch['extra_instructions']
        return {'op': 'run.start', 'args': args_out}
    if stage == 'apply':
        report_id = patch.get('report_id') or _latest_report_id(jm, ws.thread_id)
        if not report_id:
            raise HTTPException(400, 'no report_id available for apply rewind')
        args_out = {'report_id': report_id}
        if patch.get('extra_instructions'):
            args_out['extra_instructions'] = patch['extra_instructions']
        return {'op': 'apply.start', 'args': args_out}
    if stage == 'abtest':
        apply_row = _latest_succeeded(jm, ws.thread_id, 'apply')
        eval_id, dataset_id, eval_options = _latest_eval_for_abtest(jm, ws.thread_id)
        if not apply_row or not eval_id or not dataset_id:
            raise HTTPException(400, 'no apply/eval available for abtest rewind')
        op = {
            'op': 'abtest.create',
            'args': {'apply_id': apply_row['id'], 'baseline_eval_id': eval_id, 'dataset_id': dataset_id},
        }
        if eval_options:
            op['args']['eval_options'] = eval_options
        result = (apply_row.get('payload') or {}).get('result') or {}
        if result.get('candidate_chat_id'):
            op['args']['candidate_chat_id'] = result['candidate_chat_id']
        return op
    raise HTTPException(400, f'unsupported rewind stage {stage}')


def _patch_thread_inputs(ws, patch: dict) -> None:
    from evo.runtime.fs import atomic_write_json

    data = json.loads(ws.thread_meta_path.read_text(encoding='utf-8'))
    inputs = dict(data.get('inputs') or {})
    inputs.update(
        {
            k: v
            for (k, v) in patch.items()
            if k in {'num_cases', 'kb_id', 'algo_id', 'eval_name', 'target_chat_url', 'dataset_name'}
        }
    )
    data['inputs'] = inputs
    data['updated_at'] = time.time()
    atomic_write_json(ws.thread_meta_path, data)


def _thread_inputs(ws) -> dict:
    try:
        return json.loads(ws.thread_meta_path.read_text(encoding='utf-8')).get('inputs') or {}
    except Exception:
        return {}


def _latest_artifact(ws, kind: str) -> str | None:
    vals = (ws.load_artifacts() or {}).get(kind) or []
    return vals[-1] if vals else None


def _latest_succeeded(jm, thread_id: str, flow: str) -> dict | None:
    rows = _store.list_flow_tasks_by_thread(jm.store, flow, thread_id)
    for row in reversed(rows):
        if row.get('status') in {'succeeded', 'accepted'}:
            return row
    return None


def _latest_eval_id(jm, thread_id: str) -> str | None:
    row = _latest_succeeded(jm, thread_id, 'eval')
    return (row.get('payload') or {}).get('eval_id') or (row.get('payload') or {}).get('dataset_id') if row else None


def _latest_report_id(jm, thread_id: str) -> str | None:
    row = _latest_succeeded(jm, thread_id, 'run')
    return (row.get('payload') or {}).get('report_id') if row else None


def _latest_eval_for_abtest(jm, thread_id: str) -> tuple[str | None, str | None, dict]:
    row = _latest_succeeded(jm, thread_id, 'eval')
    payload = (row or {}).get('payload') or {}
    dataset_id = payload.get('dataset_id')
    eval_id = payload.get('eval_id') or dataset_id
    return (eval_id, dataset_id, dict(payload.get('eval_options') or {}))


def _regen_name(name: str) -> str:
    import re

    base = re.sub('[^A-Za-z0-9_.-]+', '_', str(name)).strip('_') or 'regen_eval'
    return f"{base}_regen_{time.strftime('%H%M%S')}"


def _abtest_report_ready(ws, row: dict | None) -> bool:
    if not row:
        return False
    out_dir = ws.dir / 'abtests' / row['id']
    return (out_dir / 'summary.md').exists() and (out_dir / 'summary.json').exists()


def _intent_summary(intent, plan) -> str:
    ops = [op.get('op') for op in plan.ops]
    if ops:
        return f"Planned operations: {', '.join((str(op) for op in ops))}"
    if plan.warnings:
        return f"No executable operation: {'; '.join(plan.warnings)}"
    return 'No executable operation was needed.'


def _auto_message(jm, thread_id: str, ws) -> str | None:
    snap = _thread_state_snapshot(jm, thread_id, ws.load_artifacts())
    for row in snap.get('active_tasks') or []:
        if row.get('status') == 'running':
            return None
    checkpoint = snap.get('pending_checkpoint') or {}
    if checkpoint:
        return _auto_checkpoint_message(ws, checkpoint)
    latest = snap.get('latest_tasks') or {}
    for flow in ('run', 'eval', 'dataset_gen', 'apply', 'abtest'):
        row = latest.get(flow) or {}
        if row.get('status') in ('failed_transient', 'paused'):
            return f"自动检查发现 {flow} 任务 {row.get('id')} 状态为 {row.get('status')}，请重试/续跑。"
    return None


def _auto_checkpoint_message(ws, checkpoint: dict) -> str:
    stage = checkpoint.get('stage') or checkpoint.get('completed_flow') or ''
    inputs = _thread_inputs(ws)
    artifacts = checkpoint.get('artifacts') or {}
    if stage == 'run' and artifacts.get('apply_ready') is False:
        return '当前分析报告的自动修改建议证据不足，请回退到 run 重新分析并补充证据。'
    if stage == 'apply' and inputs.get('auto_apply_feedback'):
        return f"回退到 apply 重新修改代码，要求：{inputs['auto_apply_feedback']}"
    if stage in {'dataset_gen', 'eval', 'run', 'apply', 'abtest'}:
        return f'继续执行 {stage} 后的下一步。'
    return '继续执行。'


def _append_message(path, role: str, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {'role': role, 'content': content, 'ts': time.time()}
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def _read_recent_messages(path, limit: int = 20) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding='utf-8').splitlines()[-limit:]:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append((str(obj.get('role', '')), str(obj.get('content', ''))))
    return rows


def _chunks(text: str, size: int = 64) -> list[str]:
    return [text[i: i + size] for i in range(0, len(text), size)] or ['']


def _sse(event: str, payload: dict) -> dict:
    return {'event': event, 'data': json.dumps({'type': event, **payload}, ensure_ascii=False, default=str)}


def _consume_task_exception(task) -> None:
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        pass


async def _cancel_when_stopped(stop: threading.Event, cancel: threading.Event) -> None:
    while not stop.is_set() and not cancel.is_set():
        await asyncio.sleep(0.1)
    if stop.is_set():
        cancel.set()


def build_router(hub: ThreadHub) -> APIRouter:
    router = APIRouter(prefix='/v1/evo')

    @router.post('/threads')
    async def create_thread(req: dict = Body(...)) -> dict:  # noqa: B008
        return await asyncio.to_thread(hub.create_thread, req)

    @router.get('/threads')
    async def list_threads() -> list[dict]:
        return hub.list_threads()

    @router.get('/threads/statuses', response_model=api_schemas.ThreadStatusList)
    async def list_thread_statuses() -> dict:
        return await asyncio.to_thread(hub.list_thread_statuses)

    @router.get('/threads/{thread_id}')
    async def get_thread(thread_id: str) -> dict:
        return hub.get_thread(thread_id)

    @router.get('/threads/{thread_id}/flow-status', response_model=api_schemas.ThreadFlowStatus)
    async def flow_status(thread_id: str) -> dict:
        return hub.flow_status(thread_id)

    @router.post('/threads/{thread_id}/messages')
    async def post_message(thread_id: str, request: Request, body: dict = Body(...)):  # noqa: B008
        content = body.get('content', '')
        if 'text/event-stream' in request.headers.get('accept', ''):
            return EventSourceResponse(hub.post_message_stream(thread_id, content))
        return await asyncio.to_thread(hub.post_message, thread_id, content)

    @router.post('/threads/{thread_id}/messages:cancel')
    async def cancel_active_message(thread_id: str) -> dict:
        return hub.cancel_message(thread_id)

    @router.post('/threads/{thread_id}/messages/{message_id}/cancel')
    async def cancel_message(thread_id: str, message_id: str) -> dict:
        return hub.cancel_message(thread_id, message_id)

    @router.post('/threads/{thread_id}/start')
    async def start_thread(thread_id: str) -> dict:
        return await asyncio.to_thread(hub.start, thread_id)

    @router.post('/threads/{thread_id}/pause')
    async def pause_thread(thread_id: str) -> dict:
        return await asyncio.to_thread(hub.pause, thread_id)

    @router.post('/threads/{thread_id}/cancel')
    async def cancel_thread(thread_id: str) -> dict:
        return await asyncio.to_thread(hub.cancel, thread_id)

    @router.post('/threads/{thread_id}/retry')
    async def retry_thread(thread_id: str) -> dict:
        return await asyncio.to_thread(hub.retry, thread_id)

    @router.post('/threads/{thread_id}/auto/step')
    async def auto_step(thread_id: str) -> dict:
        return await asyncio.to_thread(hub.auto_step, thread_id)

    @router.post('/threads/{thread_id}/auto/start')
    async def auto_start(thread_id: str, request: Request, body: dict = Body(default_factory=dict)):  # noqa: B008
        interval_s = float(body.get('interval_s', 5.0))
        if 'text/event-stream' in request.headers.get('accept', ''):
            return EventSourceResponse(hub.auto_start_stream(thread_id, interval_s=interval_s))
        return await asyncio.to_thread(hub.auto_start, thread_id, interval_s=interval_s)

    @router.post('/threads/{thread_id}/auto/stop')
    async def auto_stop(thread_id: str) -> dict:
        return await asyncio.to_thread(hub.auto_stop, thread_id)

    @router.get('/threads/{thread_id}/events')
    async def tail_events(thread_id: str, since: int = Query(0, ge=0)) -> EventSourceResponse:  # noqa: B008
        import asyncio
        from evo.service.threads.workspace import ThreadWorkspace

        path = ThreadWorkspace(hub.jm.config.storage.base_dir, thread_id, create=False).events_path

        async def gen():
            offset = since
            while True:
                if path.exists() and (size := path.stat().st_size) > offset:
                    with path.open('rb') as f:
                        f.seek(offset)
                        chunk = f.read(size - offset)
                    lines = chunk.splitlines()
                    for line in lines:
                        offset += len(line) + 1
                        text = line.decode('utf-8', 'replace').strip()
                        if text:
                            yield {'event': 'message', 'data': text, 'id': str(offset)}
                await asyncio.sleep(0.5)

        return EventSourceResponse(gen())

    return router


def mount(app, hub: ThreadHub) -> None:
    app.state.thread_hub = hub
    app.include_router(build_router(hub))
