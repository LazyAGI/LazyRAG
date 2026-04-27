from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from evo.service.core import store as _store
from evo.service.core.intent_store import IntentStore
from evo.service.core.ops_executor import OpsExecutor, Op
from evo.orchestrator.planner import Planner, PlanContext
from evo.orchestrator import capabilities as caps

if TYPE_CHECKING:
    from evo.service.core.manager import JobManager


class ThreadHub:
    def __init__(self, *, jm: 'JobManager', planner: Planner,
                 intent_store: IntentStore, ops: OpsExecutor) -> None:
        self.jm = jm
        self.planner = planner
        self.intents = intent_store
        self.ops = ops
        self._auto_threads: dict[str, threading.Event] = {}

    def list_threads(self) -> list[dict]:
        base = self.intents._base_dir.parent / 'threads'
        if not base.exists():
            return []
        return [__import__('json').loads(p.read_text(encoding='utf-8'))
                for p in sorted(base.glob('*/thread.json'))]

    def create_thread(self, payload: dict) -> dict:
        mode = payload.get('mode', 'interactive')
        if mode not in ('auto', 'interactive'):
            raise HTTPException(400, f'bad mode {mode!r}')
        import uuid, time
        tid = f'thr-{uuid.uuid4().hex[:8]}'
        from evo.service.threads.workspace import ThreadWorkspace
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, tid)
        meta = {
            'id': tid, 'mode': mode,
            'title': payload.get('title', ''),
            'inputs': payload.get('inputs') or {},
            'status': 'active',
            'created_at': time.time(), 'updated_at': time.time(),
        }
        from evo.runtime.fs import atomic_write_json
        atomic_write_json(ws.thread_meta_path, meta)
        return meta

    def get_thread(self, thread_id: str) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace, CheckpointStore, EventLog
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = __import__('json').loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        meta['artifacts'] = ws.load_artifacts()
        meta['pending_intents'] = self.intents.list_pending(thread_id)
        cps = CheckpointStore(ws, EventLog(ws.events_path))
        meta['pending_checkpoints'] = cps.list_pending()
        return meta

    def list_checkpoints(self, thread_id: str) -> list[dict]:
        from evo.service.threads.workspace import ThreadWorkspace, CheckpointStore, EventLog
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        cps = CheckpointStore(ws, EventLog(ws.events_path))
        return cps.list_pending()

    def respond_checkpoint(self, thread_id: str, cp_id: str,
                           choice: str, feedback: str | None = None) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace, CheckpointStore, EventLog
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        cps = CheckpointStore(ws, EventLog(ws.events_path))
        rec = cps.respond(cp_id, choice=choice, feedback=feedback)
        task_id = rec.get('task_id')
        if task_id and choice in ('approve', 'revise'):
            task_row = _store.get(self.jm.store, task_id)
            if task_row and task_row.get('status') == 'paused':
                self.jm.cont(task_id)
        return rec

    def post_message(self, thread_id: str, content: str) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace, EventLog
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')

        elog = EventLog(ws.events_path)
        _append_message(ws.messages_path, 'user', content)
        elog.append('user', 'user.message', {'content': content})

        ctx = self._plan_context(thread_id, ws)
        intent = self.planner.draft(content, ctx)
        self.intents.save(intent)
        _append_message(ws.messages_path, 'assistant', intent.reply)

        elog.append('assistant', 'assistant.reply', {
            'intent_id': intent.intent_id,
            'reply': intent.reply,
            'requires_confirm': intent.requires_confirm,
        })
        elog.append('intent', 'intent.pending_confirm', {
            'intent_id': intent.intent_id,
            'ops': [p.op for p in intent.suggested_ops_preview],
        })

        return {
            'intent_id': intent.intent_id,
            'reply': intent.reply,
            'requires_confirm': intent.requires_confirm,
            'preview': [
                {'op': p.op, 'humanized': p.humanized, 'safety': p.safety}
                for p in intent.suggested_ops_preview
            ],
        }

    def confirm_intent(self, thread_id: str, intent_id: str,
                       user_edit: dict | None = None) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace, EventLog
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        elog = EventLog(ws.events_path)

        intent_data = self.intents.get(intent_id)
        if intent_data is None:
            raise HTTPException(404, f'intent {intent_id} not found')

        if intent_data.get('thread_id') != thread_id:
            raise HTTPException(403, 'intent does not belong to this thread')

        self.intents.transition(intent_id, 'confirm')
        elog.append('intent', 'intent.confirmed', {'intent_id': intent_id})

        ctx = self._plan_context(thread_id, ws)
        from evo.service.core.intent_store import Intent, IntentPreview
        intent = Intent(
            intent_id=intent_data['intent_id'],
            thread_id=intent_data['thread_id'],
            user_message=intent_data['user_message'],
            reply=intent_data['reply'],
            suggested_ops_preview=[
                IntentPreview(**p) for p in intent_data.get('suggested_ops_preview', [])
            ],
            requires_confirm=intent_data['requires_confirm'],
            thinking=intent_data.get('thinking', ''),
            created_at=intent_data['created_at'],
        )
        plan = self.planner.materialize(intent, ctx, user_edit=user_edit)
        if not plan.ops:
            elog.append('plan', 'plan.failed', {
                'intent_id': intent_id,
                'code': 'PLAN_EMPTY',
                'warnings': plan.warnings,
            })
            raise HTTPException(400, {'code': 'PLAN_EMPTY',
                                      'warnings': plan.warnings})
        elog.append('plan', 'plan.materialized', {
            'intent_id': intent_id,
            'ops': [o['op'] for o in plan.ops],
            'warnings': plan.warnings,
        })

        ops = [Op(op=o['op'], args=o.get('args', {})) for o in plan.ops]
        results = self.ops.execute(ops, thread_id=intent.thread_id)

        for r in results:
            if r.status in ('submitted', 'accepted', 'continued', 'stopped', 'cancelled'):
                elog.append('op', f'op.{r.status}', {
                    'op': r.op, 'task_id': r.task_id,
                })
            else:
                elog.append('op', f'op.{r.status}', {
                    'op': r.op, 'task_id': r.task_id,
                    'error': r.error,
                })

        self.intents.transition(intent_id, 'materialize')
        return {
            'intent_id': intent_id,
            'ops_executed': len(results),
            'warnings': plan.warnings,
            'results': [
                {'op': r.op, 'status': r.status, 'task_id': r.task_id,
                 'error': r.error, 'data': r.data}
                for r in results
            ],
        }

    def auto_step(self, thread_id: str) -> dict:
        from evo.service.threads.workspace import ThreadWorkspace, EventLog
        ws = ThreadWorkspace(self.jm.config.storage.base_dir, thread_id)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = __import__('json').loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        if meta.get('mode') != 'auto':
            raise HTTPException(400, 'auto_step requires thread mode auto')
        message = _auto_message(self.jm, thread_id, ws)
        if not message:
            return {'status': 'waiting', 'message': None}
        EventLog(ws.events_path).append('auto_operator', 'auto.message',
                                        {'content': message})
        draft = self.post_message(thread_id, message)
        result = None
        if draft.get('requires_confirm') or draft.get('preview'):
            result = self.confirm_intent(thread_id, draft['intent_id'])
        return {'status': 'sent', 'message': message, 'draft': draft,
                'confirm': result}

    def auto_start(self, thread_id: str, interval_s: float = 5.0) -> dict:
        if thread_id in self._auto_threads and not self._auto_threads[thread_id].is_set():
            return {'status': 'running'}
        stop = threading.Event()
        self._auto_threads[thread_id] = stop

        def _loop() -> None:
            while not stop.is_set():
                try:
                    self.auto_step(thread_id)
                except Exception:
                    pass
                stop.wait(interval_s)

        threading.Thread(target=_loop, name=f'evo-auto-{thread_id}',
                         daemon=True).start()
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
        EventLog(ws.events_path).append('intent', 'intent.cancelled',
                                        {'intent_id': intent_id})
        return row

    def _plan_context(self, thread_id: str, ws) -> PlanContext:
        snapshot = _thread_state_snapshot(self.jm, thread_id, ws.load_artifacts())
        return PlanContext(
            thread_id=thread_id,
            recent_history=_read_recent_messages(ws.messages_path, limit=20),
            thread_state_summary=_thread_state_summary(snapshot),
            capabilities_with_safety=[
                {'op': op, 'safety': caps.get(op).safety, 'flow': caps.get(op).flow}
                for op in caps.all_ops()
            ],
            thread_state=snapshot,
        )


def _format_artifacts(artifacts: dict) -> str:
    parts: list[str] = []
    for kind in ('dataset_ids', 'eval_ids', 'run_ids', 'apply_ids',
                 'apply_commit_ids', 'merge_ids', 'deploy_ids',
                 'abtest_ids', 'chat_ids'):
        vals = artifacts.get(kind) or []
        if vals:
            parts.append(f'{kind}: {", ".join(vals[-3:])}')
    return '\n'.join(parts) if parts else ''


def _thread_state_summary(snapshot: dict) -> str:
    parts = [_format_artifacts(snapshot.get('artifacts') or {})]
    latest = snapshot.get('latest_tasks') or {}
    if latest:
        parts.append('latest_tasks: ' + json.dumps({
            k: {'id': v.get('id'), 'status': v.get('status'), 'payload': v.get('payload')}
            for k, v in latest.items()
        }, ensure_ascii=False)[:4000])
    active = snapshot.get('active_tasks') or []
    if active:
        parts.append('active_tasks: ' + ', '.join(
            f"{r['flow']}:{r['id']}:{r['status']}" for r in active[-10:]))
    reports = []
    for rid in ((snapshot.get('artifacts') or {}).get('run_ids') or [])[-3:]:
        row = latest.get('run') if (latest.get('run') or {}).get('id') == rid else None
        if row and (row.get('payload') or {}).get('report_id'):
            reports.append((row.get('payload') or {}).get('report_id'))
    if reports:
        parts.append('latest_reports: ' + ', '.join(reports))
    return '\n'.join(p for p in parts if p)


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
        if rec.get('status') not in _store.terminal_for(flow):
            active.append(rec)
    for flow, rows in rows_by_flow.items():
        if rows:
            rows.sort(key=lambda r: r.get('created_at', 0.0))
            latest[flow] = rows[-1]
    from evo.service.threads.workspace import CheckpointStore, EventLog, ThreadWorkspace
    ws = ThreadWorkspace(jm.config.storage.base_dir, thread_id)
    pending = CheckpointStore(ws, EventLog(ws.events_path)).list_pending()
    return {'artifacts': artifacts, 'active_tasks': active,
            'latest_tasks': latest, 'pending_checkpoints': pending}


def _auto_message(jm, thread_id: str, ws) -> str | None:
    snap = _thread_state_snapshot(jm, thread_id, ws.load_artifacts())
    if snap.get('pending_checkpoints'):
        return '自动检查发现有待处理 checkpoint，请批准当前 checkpoint 并继续。'
    for row in snap.get('active_tasks') or []:
        if row.get('status') == 'running':
            return None
    latest = snap.get('latest_tasks') or {}
    for flow in ('run', 'eval', 'dataset_gen', 'apply', 'abtest', 'deploy'):
        row = latest.get(flow) or {}
        if row.get('status') in ('failed_transient', 'paused'):
            return f'自动检查发现 {flow} 任务 {row.get("id")} 状态为 {row.get("status")}，请重试/续跑。'
    return None


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


def build_router(hub: ThreadHub) -> APIRouter:
    router = APIRouter(prefix='/v1/evo')

    @router.post('/threads')
    async def create_thread(req: dict = Body(...)) -> dict:
        return hub.create_thread(req)

    @router.get('/threads')
    async def list_threads() -> list[dict]:
        return hub.list_threads()

    @router.get('/threads/{thread_id}')
    async def get_thread(thread_id: str) -> dict:
        return hub.get_thread(thread_id)

    @router.post('/threads/{thread_id}/messages')
    async def post_message(thread_id: str, body: dict = Body(...)) -> dict:
        return hub.post_message(thread_id, body.get('content', ''))

    @router.post('/threads/{thread_id}/auto/step')
    async def auto_step(thread_id: str) -> dict:
        return hub.auto_step(thread_id)

    @router.post('/threads/{thread_id}/auto/start')
    async def auto_start(thread_id: str, body: dict | None = Body(default=None)) -> dict:
        return hub.auto_start(thread_id, interval_s=float((body or {}).get('interval_s', 5.0)))

    @router.post('/threads/{thread_id}/auto/stop')
    async def auto_stop(thread_id: str) -> dict:
        return hub.auto_stop(thread_id)

    @router.get('/threads/{thread_id}/intents')
    async def list_intents(thread_id: str) -> list[dict]:
        return hub.intents.list_pending(thread_id)

    @router.post('/threads/{thread_id}/intents/{intent_id}:confirm')
    @router.post('/threads/{thread_id}/intents/{intent_id}/confirm')
    async def confirm_intent(thread_id: str, intent_id: str,
                             body: dict | None = Body(default=None)) -> dict:
        return hub.confirm_intent(thread_id, intent_id,
                                  user_edit=(body or {}).get('user_edit'))

    @router.post('/threads/{thread_id}/intents/{intent_id}:cancel')
    @router.post('/threads/{thread_id}/intents/{intent_id}/cancel')
    async def cancel_intent(thread_id: str, intent_id: str) -> dict:
        return hub.cancel_intent(thread_id, intent_id)

    @router.get('/threads/{thread_id}/events')
    async def tail_events(thread_id: str,
                           since: int = Query(0, ge=0)) -> EventSourceResponse:
        import asyncio
        from evo.service.threads.workspace import ThreadWorkspace
        path = ThreadWorkspace(hub.jm.config.storage.base_dir, thread_id).events_path

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
                            yield {'event': 'message', 'data': text,
                                   'id': str(offset)}
                await asyncio.sleep(0.5)
        return EventSourceResponse(gen())

    @router.get('/threads/{thread_id}/checkpoints')
    def list_checkpoints(thread_id: str) -> list[dict]:
        return hub.list_checkpoints(thread_id)

    @router.post('/threads/{thread_id}/checkpoints/{cp_id}:respond')
    @router.post('/threads/{thread_id}/checkpoints/{cp_id}/respond')
    async def respond_checkpoint(thread_id: str, cp_id: str,
                                  body: dict = Body(...)) -> dict:
        choice = body.get('choice', 'approve')
        feedback = body.get('feedback')
        return hub.respond_checkpoint(thread_id, cp_id, choice, feedback)

    @router.get('/threads/{thread_id}/apply-commits')
    def apply_commits(thread_id: str) -> list[dict]:
        return hub.jm.apply_commits_for_thread(thread_id)

    return router


def mount(app, hub: ThreadHub) -> None:
    app.state.thread_hub = hub
    app.include_router(build_router(hub))
