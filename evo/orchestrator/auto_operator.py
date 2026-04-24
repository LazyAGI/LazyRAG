from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from evo.service import state
from evo.service.thread_workspace import (
    CheckpointStore, EventLog, ThreadWorkspace,
)

from .dispatcher import Dispatcher
from .schemas import Op

_APPLY_DONE = frozenset({'succeeded', 'accepted'})


@dataclass
class AutoInputs:
    badcase_limit: int = 200
    dataset_id: str = 'ds-default'
    baseline_eval_id: str = ''
    target_chat_url: str = ''
    on_improvement: str = 'keep'
    on_regression: str = 'keep'
    auto_apply: bool = True
    auto_abtest: bool = True


@dataclass
class Decision:
    reasoning: str
    next_op: Op | None
    terminal: bool = False
    waiting: bool = False

    def to_dict(self) -> dict:
        return {
            'reasoning': self.reasoning,
            'next_op': ({'op': self.next_op.op,
                          'args': dict(self.next_op.args)}
                         if self.next_op else None),
            'terminal': self.terminal,
            'waiting': self.waiting,
        }


@dataclass
class _Snapshot:
    artifacts: dict
    pending_checkpoints: list[dict]
    tasks: dict[str, dict]

    def has(self, kind: str) -> bool:
        return bool(self.artifacts.get(kind))


class AutoOperator:
    def __init__(self, *, thread_id: str, inputs: AutoInputs,
                 dispatcher: Dispatcher, store: state.FsStateStore,
                 workspace: ThreadWorkspace, log: EventLog,
                 checkpoints: CheckpointStore | None = None,
                 poll_interval_s: float = 0.2) -> None:
        self.thread_id = thread_id
        self.inputs = inputs
        self.dispatcher = dispatcher
        self.store = store
        self.ws = workspace
        self.log = log
        self.checkpoints = checkpoints or CheckpointStore(workspace, log)
        self.poll = poll_interval_s
        self._task: asyncio.Task | None = None
        self._cancel = False
        self._last_decision: Decision | None = None

    @property
    def last_decision(self) -> Decision | None:
        return self._last_decision

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._cancel = False
        self._task = asyncio.create_task(self._run(),
                                          name=f'auto:{self.thread_id}')
        return self._task

    async def stop(self) -> None:
        self._cancel = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def decide(self) -> Decision:
        decision = self._compute(self._snapshot())
        self._last_decision = decision
        self.log.append('auto_user', 'decision', decision.to_dict())
        return decision

    async def _run(self) -> None:
        self.log.append('auto_user', 'started', {'inputs': asdict(self.inputs)})
        try:
            while not self._cancel:
                d = self.decide()
                if d.terminal:
                    self.log.append('auto_user', 'finished', {})
                    return
                if d.waiting:
                    await asyncio.sleep(self.poll)
                    continue
                await asyncio.to_thread(self.dispatcher.dispatch, [d.next_op])
                await self._wait_pending_settle()
        except asyncio.CancelledError:
            self.log.append('auto_user', 'paused', {})
            raise

    # ---- snapshot / decision ---------------------------------------------

    def _snapshot(self) -> _Snapshot:
        artifacts = self.ws.load_artifacts()
        pending = self.checkpoints.list_pending()
        return _Snapshot(artifacts=artifacts, pending_checkpoints=pending,
                          tasks=self._latest_tasks(artifacts))

    def _latest_tasks(self, artifacts: dict) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for kind, flow in (('run_ids', 'run'), ('apply_ids', 'apply'),
                            ('eval_ids', 'eval'), ('abtest_ids', 'abtest')):
            for tid in reversed(artifacts.get(kind) or []):
                if flow not in {'run', 'apply', 'abtest', 'eval'}:
                    continue
                rec = state.get(self.store, tid)
                if rec is not None:
                    out[flow] = rec
                    break
        return out

    def _compute(self, s: _Snapshot) -> Decision:
        if s.pending_checkpoints:
            cp = s.pending_checkpoints[0]
            return Decision(f"resolve checkpoint {cp['id']} ({cp['kind']})",
                             Op('checkpoint.respond',
                                 {'cp_id': cp['id'], 'choice': 'approve',
                                  'responder': 'auto_user'}))

        for flow in ('eval', 'run', 'apply', 'abtest'):
            rec = s.tasks.get(flow)
            if rec is None:
                continue
            status = rec['status']
            if status == 'paused':
                return Decision(f'{flow} paused, resume',
                                 Op(f'{flow}.continue',
                                     {'task_id': rec['id']}))
            if status in ('running', 'queued', 'stopping'):
                return Decision(f'{flow} {status}, wait', None, waiting=True)
            if status == 'failed_transient':
                return Decision(f'{flow} transient failure, retry',
                                 Op(f'{flow}.continue',
                                     {'task_id': rec['id']}))
            if status == 'failed_permanent':
                return Decision(f'{flow} permanent failure, abort',
                                 None, terminal=True)

        if not s.has('eval_ids'):
            return Decision(self._eval_reasoning(),
                             self._eval_op())

        if not s.has('run_ids'):
            return Decision('run analysis on latest eval',
                             Op('run.start',
                                 {'badcase_limit': self.inputs.badcase_limit}))

        if (s.tasks.get('run', {}).get('status') == 'succeeded'
                and self.inputs.auto_apply and not s.has('apply_ids')):
            run_rec = s.tasks['run']
            args: dict[str, Any] = {}
            if run_rec.get('report_id'):
                args['report_id'] = run_rec['report_id']
            return Decision('apply code modification from run report',
                             Op('apply.start', args))

        apply_done = s.tasks.get('apply', {}).get('status') in _APPLY_DONE
        if (self.inputs.auto_abtest and apply_done
                and self.inputs.baseline_eval_id and not s.has('abtest_ids')):
            return Decision('compare apply against baseline via abtest',
                             Op('abtest.create',
                                 {'apply_id': s.tasks['apply']['id'],
                                  'baseline_eval_id': self.inputs.baseline_eval_id,
                                  'dataset_id': self.inputs.dataset_id}))

        ab = s.tasks.get('abtest')
        if ab and ab['status'] == 'succeeded':
            verdict = (ab.get('payload') or {}).get('verdict')
            cand = (ab.get('payload') or {}).get('candidate_chat_id')
            if cand and self._role_of(cand) == 'candidate':
                if verdict == 'improved' and self.inputs.on_improvement == 'promote':
                    return Decision(f'promote candidate {cand}',
                                     Op('chat.promote', {'chat_id': cand}))
                if verdict == 'regressed' and self.inputs.on_regression == 'retire':
                    return Decision(f'retire candidate {cand}',
                                     Op('chat.retire', {'chat_id': cand}))

        return Decision('pipeline complete', None, terminal=True)

    def _eval_reasoning(self) -> str:
        if self.inputs.baseline_eval_id:
            return f'fetch baseline eval {self.inputs.baseline_eval_id}'
        return f'run new eval on dataset {self.inputs.dataset_id}'

    def _eval_op(self) -> Op:
        if self.inputs.baseline_eval_id:
            return Op('eval.fetch', {'eval_id': self.inputs.baseline_eval_id})
        return Op('eval.run',
                   {'dataset_id': self.inputs.dataset_id,
                    'target_chat_url': self.inputs.target_chat_url})

    # ---- helpers ---------------------------------------------------------

    def _role_of(self, chat_id: str) -> str | None:
        registry = getattr(self.dispatcher.jm, 'chat_registry', None)
        if registry is None:
            return None
        inst = registry.get(chat_id)
        return inst.role if inst else None

    async def _wait_pending_settle(self) -> None:
        deadline = time.time() + 30 * 60
        while time.time() < deadline:
            if self._cancel:
                return
            snap = self._snapshot()
            still_running = any(
                rec['status'] in ('running', 'queued', 'stopping')
                for rec in snap.tasks.values()
            )
            if not still_running:
                return
            await asyncio.sleep(self.poll)
