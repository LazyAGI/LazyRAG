from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Iterable

from evo.service.thread_workspace import EventLog

from .dispatcher import Dispatcher
from .prompts import build_prompt
from .schemas import Op, OpResult, TurnResult
from .think_stream import ThinkSplitter

LLM = Callable[[str], AsyncIterator[str]]


@dataclass
class StreamEvent:
    kind: str   # 'thinking' | 'action' | 'answer' | 'cancelled' | 'done'
    text: str = ''
    payload: dict | None = None


_OPEN_TAGS = (('<answer>', 'answer'), ('<ops>', 'ops'))
_CLOSE = {'answer': '</answer>', 'ops': '</ops>'}


class _SectionStreamer:
    def __init__(self) -> None:
        self.buf = ''
        self.section: str | None = None
        self.flushed = 0
        self.ops_raw: str | None = None
        self.answer = ''

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self.buf += chunk
        out: list[tuple[str, str]] = []
        while self._step(out):
            pass
        return out

    def _step(self, out: list[tuple[str, str]]) -> bool:
        if self.section is None:
            for tag, name in _OPEN_TAGS:
                pos = self.buf.find(tag, self.flushed)
                if pos != -1:
                    self.section = name
                    self.flushed = pos + len(tag)
                    return True
            return False
        close = _CLOSE[self.section]
        end = self.buf.find(close, self.flushed)
        if self.section == 'ops':
            if end == -1:
                return False
            self.ops_raw = self.buf[self.flushed:end].strip()
        else:
            if end == -1:
                safe = max(self.flushed, len(self.buf) - (len(close) - 1))
                if safe > self.flushed:
                    text = self.buf[self.flushed:safe]
                    self.flushed = safe
                    self.answer += text
                    out.append(('answer', text))
                return False
            text = self.buf[self.flushed:end]
            if text:
                self.answer += text
                out.append(('answer', text))
        self.flushed = end + len(close)
        self.section = None
        return True

    def parse_ops(self) -> list[Op]:
        if not self.ops_raw:
            return []
        try:
            data = json.loads(self.ops_raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        ops: list[Op] = []
        for entry in data:
            if isinstance(entry, dict) and 'op' in entry:
                ops.append(Op(op=str(entry['op']),
                              args=dict(entry.get('args') or {}),
                              rationale=str(entry.get('rationale') or '')))
        return ops


def _action_event(op: Op, result: OpResult) -> StreamEvent:
    return StreamEvent('action', payload={
        'op': op.op, 'summary': result.summary,
        'status': result.status, 'task_id': result.task_id,
    })


class ConversationAgent:
    def __init__(self, *, llm: LLM, dispatcher: Dispatcher,
                 log: EventLog | None = None,
                 history_provider: Callable[[], Iterable[tuple[str, str]]] | None = None,
                 state_provider: Callable[[], str] | None = None) -> None:
        self.llm = llm
        self.dispatcher = dispatcher
        self.log = log
        self.history_provider = history_provider or (lambda: ())
        self.state_provider = state_provider or (lambda: '')

    async def converse(self, user_message: str) -> AsyncIterator[StreamEvent]:
        prompt = build_prompt(
            user_message=user_message,
            thread_state=self.state_provider(),
            history=self.history_provider(),
        )
        think = ThinkSplitter()
        sections = _SectionStreamer()
        thinking = ''
        results: list[OpResult] = []
        try:
            async for chunk in self.llm(prompt):
                segments = think.feed(chunk)
                for kind, text in segments:
                    if kind == 'think':
                        thinking += text
                        yield StreamEvent('thinking', text)
                        if self.log:
                            self.log.append('agent', 'thinking.delta',
                                            {'text': text})
                        continue
                    for skind, stext in sections.feed(text):
                        yield StreamEvent(skind, stext)
                if sections.ops_raw is not None and not results:
                    ops = sections.parse_ops()
                    if self.log:
                        self.log.append('agent', 'plan',
                                        {'ops': [vars(o) for o in ops]})
                    for op, result in zip(ops, self.dispatcher.dispatch(ops)):
                        results.append(result)
                        yield _action_event(op, result)
                        if result.status == 'failed':
                            break
            for kind, text in think.flush():
                if kind == 'think':
                    thinking += text
                    yield StreamEvent('thinking', text)
                else:
                    for skind, stext in sections.feed(text):
                        yield StreamEvent(skind, stext)
        except asyncio.CancelledError:
            yield StreamEvent('cancelled', payload={
                'thinking_partial': thinking,
                'answer_partial': sections.answer,
                'dispatched': [r.task_id for r in results if r.task_id],
            })
            if self.log:
                self.log.append('agent', 'interrupted',
                                {'dispatched': [r.task_id for r in results if r.task_id]})
            raise
        yield StreamEvent('done', payload={
            'thinking': thinking,
            'answer': sections.answer,
            'op_results': [vars(r) for r in results],
        })


@dataclass
class AgentTurn:
    agent: ConversationAgent
    user_message: str
    _task: asyncio.Task | None = None
    cancelled: bool = False
    final: TurnResult | None = None

    async def stream(self) -> AsyncIterator[StreamEvent]:
        queue: asyncio.Queue = asyncio.Queue()

        async def _run() -> None:
            try:
                async for ev in self.agent.converse(self.user_message):
                    await queue.put(ev)
            except asyncio.CancelledError:
                pass
            await queue.put(None)

        self._task = asyncio.create_task(_run(), name='agent.turn')
        thinking, answer = '', ''
        while True:
            ev = await queue.get()
            if ev is None:
                break
            if ev.kind == 'thinking':
                thinking += ev.text
            elif ev.kind == 'answer':
                answer += ev.text
            elif ev.kind == 'done':
                p = ev.payload or {}
                self.final = TurnResult(
                    thinking=p.get('thinking', thinking),
                    answer=p.get('answer', answer),
                    op_results=list(p.get('op_results') or []),
                    interrupted=False,
                )
            elif ev.kind == 'cancelled':
                self.cancelled = True
                self.final = TurnResult(
                    thinking=thinking, answer=answer,
                    op_results=[], interrupted=True,
                )
            yield ev

    def cancel(self) -> None:
        self.cancelled = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
