from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import replace
from typing import Any, AsyncIterator, Callable

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from evo.orchestrator import (
    AgentTurn, AutoInputs, AutoOperator, AutoTurn, ConversationAgent, Dispatcher,
)
from evo.orchestrator.llm import make_auto_user_llm, make_evo_llm
from evo.runtime.config import EvoConfig
from evo.service.jobs import JobManager
from evo.service.thread_workspace import (
    CheckpointStore, EventLog, ThreadLocks, ThreadWorkspace,
)

from evo.runtime.fs import atomic_write_json as _atomic_write_json


class ThreadCreate(BaseModel):
    mode: str = 'interactive'
    title: str | None = None
    inputs: dict[str, Any] | None = None
    start_auto: bool = True


class MessageIn(BaseModel):
    content: str


class CheckpointResponse(BaseModel):
    choice: str
    feedback: str | None = None
    responder: str = 'user'


def _append_message(ws: ThreadWorkspace, role: str, content: str) -> None:
    line = json.dumps({'role': role, 'content': content,
                        'ts': time.time()}, ensure_ascii=False) + '\n'
    with open(ws.messages_path, 'a', encoding='utf-8') as f:
        f.write(line)


def _sse(event: str, payload: dict | None) -> dict:
    return {'event': event,
            'data': json.dumps(payload or {}, ensure_ascii=False, default=str)}


class ThreadHub:
    def __init__(self, *, jm: JobManager, cfg: EvoConfig,
                 llm_factory: Callable[[], Callable[[str], Any]],
                 auto_user_llm_factory: Callable[
                     [], Callable[[str], Any]] | None = None) -> None:
        self.jm = jm
        self.cfg = cfg
        self.llm_factory = llm_factory
        self._au_factory = auto_user_llm_factory or make_auto_user_llm(cfg)
        self.locks = ThreadLocks()
        self._active_turn: dict[str, AgentTurn] = {}
        self._auto_ops: dict[str, AutoOperator] = {}

    def workspace(self, thread_id: str) -> ThreadWorkspace:
        return ThreadWorkspace(self.cfg.storage.base_dir, thread_id)

    def event_log(self, thread_id: str) -> EventLog:
        return EventLog(self.workspace(thread_id).events_path)

    def checkpoints(self, thread_id: str) -> CheckpointStore:
        return CheckpointStore(self.workspace(thread_id),
                                self.event_log(thread_id))

    def list_threads(self) -> list[dict]:
        base = self.cfg.storage.base_dir / 'state' / 'threads'
        if not base.exists():
            return []
        return [json.loads(p.read_text(encoding='utf-8'))
                for p in sorted(base.glob('*/thread.json'))]

    def create_thread(self, payload: ThreadCreate) -> dict:
        if payload.mode not in ('auto', 'interactive'):
            raise HTTPException(400, f'bad mode {payload.mode!r}')
        tid = f'thr-{uuid.uuid4().hex[:8]}'
        ws = self.workspace(tid)
        meta = {
            'id': tid, 'mode': payload.mode,
            'title': payload.title or '',
            'inputs': payload.inputs or {},
            'status': 'active',
            'created_at': time.time(), 'updated_at': time.time(),
        }
        _atomic_write_json(ws.thread_meta_path, meta)
        self.event_log(tid).append('system', 'thread.created',
                                    {'mode': payload.mode})
        if payload.mode == 'auto' and payload.start_auto:
            self._start_auto(tid, payload.inputs or {})
        return meta

    def get_thread(self, thread_id: str) -> dict:
        ws = self.workspace(thread_id)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = json.loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        meta['artifacts'] = ws.load_artifacts()
        meta['pending_checkpoints'] = self.checkpoints(thread_id).list_pending()
        return meta

    def post_message(self, thread_id: str, content: str) -> AsyncIterator[dict]:
        ws = self.workspace(thread_id)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = json.loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        return self._stream_message(thread_id, content,
                                     self.event_log(thread_id), meta, 'user')

    async def run_auto_synthetic(self, thread_id: str, content: str) -> None:
        ws = self.workspace(thread_id)
        if not ws.thread_meta_path.exists():
            raise HTTPException(404, f'thread {thread_id} not found')
        meta = json.loads(ws.thread_meta_path.read_text(encoding='utf-8'))
        if meta.get('mode') != 'auto':
            raise HTTPException(400, 'not an auto thread')
        log = self.event_log(thread_id)
        log.append('auto_user', 'message', {'content': content})
        _append_message(ws, 'auto_user', content)
        turn = AgentTurn(
            agent=self._agent_for(thread_id, log),
            user_message=content,
        )
        self._active_turn[thread_id] = turn
        lock = self.locks.get(thread_id)
        await lock.acquire()
        try:
            async for _ in turn.stream():
                pass
            if turn.final is not None:
                _append_message(ws, 'agent', turn.final.answer)
        finally:
            lock.release()
            self._active_turn.pop(thread_id, None)

    async def step_auto_once(self, thread_id: str) -> AutoTurn:
        return await self.ensure_auto(thread_id).step_once()

    async def cancel_active_turn(self, thread_id: str) -> None:
        turn = self._active_turn.get(thread_id)
        if turn is not None:
            turn.cancel()
            await asyncio.sleep(0)

    async def stop_thread(self, thread_id: str) -> None:
        op = self._auto_ops.get(thread_id)
        if op is not None:
            await op.stop()

    def respond_checkpoint(self, thread_id: str, cp_id: str,
                            choice: str, *, feedback: str | None,
                            responder: str) -> dict:
        return self.checkpoints(thread_id).respond(
            cp_id, choice=choice, feedback=feedback, responder=responder)

    def _message_pairs(self, thread_id: str) -> list[tuple[str, str]]:
        p = self.workspace(thread_id).messages_path
        if not p.is_file():
            return []
        lines = p.read_text(encoding='utf-8', errors='replace').splitlines()[-64:]
        out: list[tuple[str, str]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            r, c = o.get('role', ''), o.get('content', '')
            if r in ('user', 'auto_user', 'agent') and c:
                out.append((str(r), str(c)))
        return out

    def _thread_state_str(self, thread_id: str) -> str:
        try:
            m = self.get_thread(thread_id)
        except Exception:
            return ''
        m.pop('title', None)
        m.pop('created_at', None)
        s = json.dumps(m, ensure_ascii=False, default=str)
        return s[: 12000]

    def _agent_for(self, thread_id: str, log: EventLog) -> ConversationAgent:
        return ConversationAgent(
            llm=self.llm_factory(),
            dispatcher=Dispatcher(
                jm=self.jm, base_dir=self.cfg.storage.base_dir,
                log=log, thread_id=thread_id,
            ),
            log=log,
            history_provider=lambda: self._message_pairs(thread_id),
            state_provider=lambda: self._thread_state_str(thread_id),
        )

    def auto(self, thread_id: str) -> AutoOperator | None:
        return self._auto_ops.get(thread_id)

    def ensure_auto(self, thread_id: str) -> AutoOperator:
        op = self._auto_ops.get(thread_id)
        if op is not None:
            return op
        meta = json.loads(self.workspace(thread_id).thread_meta_path
                           .read_text(encoding='utf-8'))
        return self._build_auto(thread_id, meta.get('inputs') or {})

    def _build_auto(self, thread_id: str, inputs: dict) -> AutoOperator:
        log = self.event_log(thread_id)
        disp = Dispatcher(jm=self.jm, base_dir=self.cfg.storage.base_dir,
                            log=log, thread_id=thread_id)
        u = {k: v for k, v in (inputs or {}).items()
              if k in AutoInputs.__dataclass_fields__}
        op = AutoOperator(
            thread_id=thread_id,
            inputs=replace(AutoInputs(), **u) if u else AutoInputs(),
            store=self.jm.store,
            workspace=self.workspace(thread_id), log=log, cfg=self.cfg,
            run_synthetic=lambda c: self.run_auto_synthetic(thread_id, c),
            user_message_llm=self._au_factory,
            checkpoints=self.checkpoints(thread_id),
        )
        op._attach_dispatcher(disp)
        self._auto_ops[thread_id] = op
        return op

    def _start_auto(self, thread_id: str, inputs: dict) -> None:
        self._build_auto(thread_id, inputs).start()

    async def _stream_message(self, thread_id: str, content: str,
                                log: EventLog, meta: dict, role: str
                                ) -> AsyncIterator[dict]:
        if meta.get('mode') == 'auto' and role == 'user':
            yield _sse('error', {'message': 'auto mode does not accept user messages'})
            return
        await self.cancel_active_turn(thread_id)
        ws = self.workspace(thread_id)
        if role == 'user':
            log.append('user', 'message', {'content': content})
            _append_message(ws, 'user', content)
        turn = AgentTurn(
            agent=self._agent_for(thread_id, log),
            user_message=content,
        )
        self._active_turn[thread_id] = turn
        lock = self.locks.get(thread_id)
        await lock.acquire()
        try:
            async for ev in turn.stream():
                yield _sse(ev.kind, {'text': ev.text, 'payload': ev.payload})
            if turn.final is not None:
                _append_message(ws, 'agent', turn.final.answer)
        finally:
            lock.release()
            self._active_turn.pop(thread_id, None)


def build_router(hub: ThreadHub) -> APIRouter:
    router = APIRouter(prefix='/v1/evo')

    @router.post('/threads')
    async def create_thread(req: ThreadCreate = Body(...)) -> dict:
        return hub.create_thread(req)

    @router.get('/threads')
    async def list_threads() -> list[dict]:
        return hub.list_threads()

    @router.get('/threads/{thread_id}')
    async def get_thread(thread_id: str) -> dict:
        return hub.get_thread(thread_id)

    @router.post('/threads/{thread_id}/messages')
    async def post_message(thread_id: str,
                            req: MessageIn = Body(...)) -> EventSourceResponse:
        async def gen() -> AsyncIterator[dict]:
            async for ev in hub.post_message(thread_id, req.content):
                yield ev
        return EventSourceResponse(gen())

    @router.post('/threads/{thread_id}/agent/cancel')
    async def cancel_agent(thread_id: str) -> dict:
        await hub.cancel_active_turn(thread_id)
        return {'ok': True}

    @router.post('/threads/{thread_id}/stop')
    async def stop_thread(thread_id: str) -> dict:
        await hub.stop_thread(thread_id)
        return {'ok': True}

    @router.get('/threads/{thread_id}/checkpoints')
    async def list_pending(thread_id: str) -> list[dict]:
        return hub.checkpoints(thread_id).list_pending()

    @router.post('/threads/{thread_id}/checkpoints/{cp_id}/respond')
    async def respond_cp(thread_id: str, cp_id: str,
                          req: CheckpointResponse = Body(...)) -> dict:
        return hub.respond_checkpoint(thread_id, cp_id, req.choice,
                                        feedback=req.feedback,
                                        responder=req.responder)

    @router.get('/threads/{thread_id}/auto/decision')
    async def get_decision(thread_id: str) -> dict:
        op = hub.auto(thread_id)
        if op is None:
            raise HTTPException(404, 'no auto operator')
        t = op.last_turn
        if t is not None:
            return t.to_dict()
        d = op.last_decision
        if d is not None and hasattr(d, 'to_dict'):
            return d.to_dict()
        raise HTTPException(404, 'no turn yet')

    @router.post('/threads/{thread_id}/auto/step')
    async def step_decision(thread_id: str) -> dict:
        r = await hub.step_auto_once(thread_id)
        return r.to_dict()

    @router.get('/threads/{thread_id}/events')
    async def tail_events(thread_id: str,
                           since: int = Query(0, ge=0)) -> EventSourceResponse:
        path = hub.workspace(thread_id).events_path

        async def gen() -> AsyncIterator[dict]:
            offset = since
            while True:
                if path.exists() and (size := path.stat().st_size) > offset:
                    with path.open('rb') as f:
                        f.seek(offset)
                        chunk = f.read(size - offset)
                    offset = size
                    for line in chunk.splitlines():
                        text = line.decode('utf-8', 'replace').strip()
                        if text:
                            yield {'event': 'message', 'data': text,
                                   'id': str(offset)}
                await asyncio.sleep(0.5)
        return EventSourceResponse(gen())

    return router


def mount(app: FastAPI, hub: ThreadHub) -> None:
    app.state.thread_hub = hub
    app.include_router(build_router(hub))
