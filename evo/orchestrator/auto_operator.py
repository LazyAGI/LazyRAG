from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable

from evo.runtime.config import EvoConfig
from evo.service.core import store as state
from evo.service.threads.workspace import (
    CheckpointStore, EventLog, ThreadWorkspace,
)

from .schemas import Op

_APPLY_DONE = frozenset({'succeeded', 'accepted'})
_DEFAULT_KINDS = frozenset({
    'eval.complete', 'checkpoint.required', 'apply.round', 'apply.complete', 'phase.completed',
})


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
    poll_interval_s: float = 0.2
    dedupe_s: float = 2.0
    max_event_bytes: int = 12000
    max_telemetry_bytes: int = 8000
    run_telemetry: bool = True
    event_kinds: frozenset[str] | None = None
    max_turns: int = 0


@dataclass
class AutoTurn:
    trigger: str | None
    user_message: str
    waiting: bool = False
    terminal: bool = False
    pipeline_done: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        r = self.trigger or ''
        return {
            'trigger': self.trigger, 'user_message': self.user_message,
            'reasoning': r, 'next_op': None,
            'waiting': self.waiting, 'terminal': self.terminal,
            'pipeline_done': self.pipeline_done, 'error': self.error,
        }


class AutoOperator:
    def __init__(
        self, *, thread_id: str, inputs: AutoInputs,
        store: state.FsStateStore, workspace: ThreadWorkspace, log: EventLog,
        cfg: EvoConfig,
        run_synthetic: Callable[[str], Awaitable[None]],
        user_message_llm: Callable[[], Callable[[str], Any]] | None = None,
        checkpoints: CheckpointStore | None = None,
        user_message_fn: Callable[[str, dict], Awaitable[str]] | None = None,
    ) -> None:
        self.thread_id = thread_id
        self.inputs = inputs
        self.store = store
        self.ws = workspace
        self.log = log
        self.cfg = cfg
        self._run_synthetic = run_synthetic
        self._um_llm = user_message_llm
        self._um_fn = user_message_fn
        self.checkpoints = checkpoints or CheckpointStore(workspace, log)
        self.poll = inputs.poll_interval_s
        self._task: asyncio.Task | None = None
        self._cancel = False
        self._last: AutoTurn | None = None
        self._ev_seq: int = 0
        self._run_line: dict[str, int] = {}
        self._fired: dict[str, float] = {}
        self._boot_eval_ok: bool = False
        self._turns = 0
        self._kinds = inputs.event_kinds or _DEFAULT_KINDS
        self._role_jm: Any = None
        self._dispatcher: Any = None

    def _attach_dispatcher(self, d: Any) -> None:
        self._dispatcher = d
        self._role_jm = getattr(d, 'jm', None)

    @property
    def last_turn(self) -> AutoTurn | None:
        return self._last

    @property
    def last_decision(self) -> Any:
        if self._last is None:
            return None
        t = self._last
        return {'reasoning': t.trigger or 'idle', 'user_message': t.user_message,
                'waiting': t.waiting, 'terminal': t.terminal, 'next_op': None}

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._cancel = False
        self._task = asyncio.create_task(self._run(), name=f'auto:{self.thread_id}')
        return self._task

    async def stop(self) -> None:
        self._cancel = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def step_once(self) -> AutoTurn:
        if self._pipeline_done():
            t = AutoTurn(None, '', terminal=True, pipeline_done=True)
            self._last = t
            return t
        tr = self._next_trigger()
        if tr is None:
            t = AutoTurn(None, '', waiting=True)
            self._last = t
            return t
        tkey, tdata = tr[0], tr[1]
        if not self._dedupe(tkey):
            t = AutoTurn(tkey, '', waiting=True)
            self._last = t
            return t
        ctx = _build_context(
            tkey, tdata, self.ws, self.store, self.cfg, self._run_line,
            self.checkpoints, self.inputs)
        if len(ctx) > self.inputs.max_event_bytes:
            ctx = ctx[: self.inputs.max_event_bytes] + '…'
        self.log.append('auto_user', 'context', {'blob_len': len(ctx), 't': tkey})
        try:
            um = (await self._um_fn(tkey, tdata)) if self._um_fn else await self._gen_user(ctx)
        except Exception as e:
            t = AutoTurn(tkey, '', error=str(e))
            self._last = t
            self.log.append('auto_user', 'synthetic_error', {'error': str(e)})
            return t
        self._mark_fired(tkey)
        self._bump_after(tdata)
        self.log.append('auto_user', 'synthetic', {'content': um})
        try:
            await self._run_synthetic(um)
        except Exception as e:
            t2 = AutoTurn(tkey, um, error=str(e))
            self._last = t2
            self.log.append('auto_user', 'turn_error', {'error': str(e)})
            return t2
        self._turns += 1
        if tkey == 'bootstrap:eval':
            self._boot_eval_ok = True
        r = AutoTurn(tkey, um)
        self._last = r
        return r

    def decide(self) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.step_once())
        raise RuntimeError('use await step_once() in async code')

    async def _gen_user(self, ctx: str) -> str:
        if not self._um_llm:
            raise RuntimeError('no user_message_llm')
        llm = self._um_llm()
        out: list[str] = []
        async for ch in llm(ctx):
            out.append(ch)
        return ''.join(ch).strip() or '请继续。'

    async def _run(self) -> None:
        self._catchup_events()
        self.log.append('auto_user', 'started', {'inputs': asdict(self.inputs)})
        try:
            while not self._cancel:
                if self.inputs.max_turns and self._turns >= self.inputs.max_turns:
                    self.log.append('auto_user', 'finished', {'reason': 'max_turns'})
                    return
                if self._pipeline_done() and not self._has_pending_work():
                    self.log.append('auto_user', 'finished', {'reason': 'pipeline_done'})
                    return
                t = await self.step_once()
                if t.error:
                    pass
                if t.waiting and not t.user_message:
                    await asyncio.sleep(self.poll)
                    continue
                if t.terminal and t.pipeline_done:
                    return
                if t.waiting:
                    await asyncio.sleep(self.poll)
        except asyncio.CancelledError:
            self.log.append('auto_user', 'paused', {})
            raise

    def _catchup_events(self) -> None:
        p = self.ws.events_path
        if not p.is_file():
            return
        m = self._ev_seq
        for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
            if not line.strip():
                continue
            try:
                m = max(m, int(json.loads(line).get('seq') or 0))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        self._ev_seq = m

    def _next_trigger(self) -> tuple[str, Any] | None:
        p = self.ws.events_path
        if p.exists() and p.stat().st_size:
            for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seq = int(ev.get('seq') or 0)
                if seq <= self._ev_seq:
                    continue
                k = str(ev.get('kind') or '')
                if k in self._kinds and self._kind_match(k, ev):
                    return (f'event:{k}:{seq}', (seq, ev))
        if self.inputs.run_telemetry:
            for rid in reversed((self.ws.load_artifacts().get('run_ids') or [])):
                tel = self.cfg.storage.runs_dir / rid / 'telemetry.jsonl'
                if not tel.is_file():
                    continue
                lines = tel.read_text(encoding='utf-8', errors='replace').splitlines()
                cur = self._run_line.get(rid, 0)
                for j in range(cur, len(lines)):
                    try:
                        o = json.loads(lines[j])
                    except json.JSONDecodeError:
                        continue
                    if o.get('type') in ('stage.completed', 'agent_run'):
                        return (f'tel:{rid}:{j}', (rid, o, j + 1))
        if not self._boot_eval_ok and not (self.ws.load_artifacts().get('eval_ids') or []):
            t = self._latest_tasks()
            e = t.get('eval')
            st = (e or {}).get('status')
            if e is None or st in (None, 'failed_permanent', 'cancelled', 'rejected'):
                return ('bootstrap:eval', ('bootstrap', {}))
        return None

    def _bump_after(self, data: Any) -> None:
        if isinstance(data, tuple) and len(data) == 2 and isinstance(data[0], int):
            self._ev_seq = max(self._ev_seq, data[0])
        if isinstance(data, tuple) and len(data) == 3:
            rid, _o, nxtl = data
            self._run_line[rid] = nxtl

    def _dedupe(self, key: str) -> bool:
        now = time.time()
        self._fired = {k: t for k, t in self._fired.items() if now - t < 600}
        t0 = self._fired.get(key, 0)
        if t0 and now - t0 < self.inputs.dedupe_s:
            return False
        return True

    def _mark_fired(self, key: str) -> None:
        self._fired[key] = time.time()

    def _kind_match(self, k: str, ev: dict) -> bool:
        if k == 'phase.completed':
            return str(ev.get('actor', '')).startswith('abtest:')
        return True

    def _has_pending_work(self) -> bool:
        if self.checkpoints.list_pending():
            return True
        for flow in ('eval', 'run', 'apply', 'abtest', 'dataset_gen', 'merge', 'deploy'):
            r = self._latest_tasks().get(flow)
            if r and r.get('status') in (
                    'running', 'queued', 'stopping', 'paused', 'failed_transient'):
                return True
        return False

    def _latest_tasks(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        a = self.ws.load_artifacts()
        for kind, flow in (('run_ids', 'run'), ('apply_ids', 'apply'),
                            ('eval_ids', 'eval'), ('abtest_ids', 'abtest'),
                            ('dataset_ids', 'dataset_gen'), ('merge_ids', 'merge'),
                            ('deploy_ids', 'deploy')):
            for tid in reversed(a.get(kind) or []):
                r = state.get(self.store, tid)
                if r is not None:
                    out[flow] = r
                    break
        return out

    def _pipeline_done(self) -> bool:
        if self.checkpoints.list_pending():
            return False
        tasks = self._latest_tasks()
        for flow in ('eval', 'run', 'apply', 'abtest', 'dataset_gen', 'merge', 'deploy'):
            rec = tasks.get(flow)
            if not rec:
                continue
            st = rec['status']
            if st in ('running', 'queued', 'stopping', 'paused', 'failed_transient'):
                return False
            if st == 'failed_permanent':
                return True
        arts = self.ws.load_artifacts()
        if not arts.get('eval_ids'):
            return False
        if not arts.get('run_ids'):
            return False
        if (tasks.get('run', {}).get('status') == 'succeeded' and self.inputs.auto_apply
                and not arts.get('apply_ids')):
            return False
        ar = tasks.get('apply', {})
        apply_done = ar.get('status') in _APPLY_DONE
        if (self.inputs.auto_abtest and apply_done
                and self.inputs.baseline_eval_id and not arts.get('abtest_ids')):
            return False
        ab = tasks.get('abtest')
        if ab and ab.get('status') == 'succeeded':
            verdict = (ab.get('payload') or {}).get('verdict')
            cand = (ab.get('payload') or {}).get('candidate_chat_id')
            if cand and self._role_of(cand) == 'candidate':
                if verdict == 'improved' and self.inputs.on_improvement == 'promote':
                    return False
                if verdict == 'regressed' and self.inputs.on_regression == 'retire':
                    return False
        return True

    def _role_of(self, chat_id: str) -> str | None:
        jm = self._role_jm
        if jm is None:
            return None
        reg = getattr(jm, 'chat_registry', None)
        if reg is None:
            return None
        inst = reg.get(chat_id)
        return inst.role if inst else None


def _build_context(
    tr_name: str, data: Any, ws: ThreadWorkspace, store: Any, cfg: EvoConfig,
    run_line: dict[str, int], cps: CheckpointStore, inputs: AutoInputs,
) -> str:
    parts: list[str] = [f'trigger:{tr_name}', f'thread_id:{ws.thread_id}']
    if data == ('bootstrap', {}):
        parts.append('bootstrap: need first eval; inputs.dataset_id and baseline_eval_id apply')
    elif isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
        ev = data[1]
        parts.append('event:' + json.dumps(ev, ensure_ascii=False)[: 4000])
    elif isinstance(data, tuple) and len(data) == 3:
        rid, o, _ = data
        parts.append('run_telemetry ' + str(rid) + ':' + json.dumps(o, ensure_ascii=False)[: 4000])
    arts = ws.load_artifacts()
    parts.append('artifacts:' + json.dumps(arts, ensure_ascii=False))
    parts.append('pending_checkpoints:' + str(len(cps.list_pending())))
    for fl in 'eval', 'run', 'apply', 'abtest', 'dataset_gen', 'merge', 'deploy':
        key = f'{fl}_ids' if fl != 'eval' else 'eval_ids'
        for tid in reversed(arts.get(key) or []):
            rec = state.get(store, tid)
            if rec:
                parts.append(f'{fl}:{json.dumps(rec, ensure_ascii=False)[: 2000]}')
                break
    for rid in reversed(arts.get('run_ids') or []):
        tpath = cfg.storage.runs_dir / rid / 'telemetry.jsonl'
        if tpath.is_file():
            li = run_line.get(rid, 0)
            tlines = tpath.read_text(encoding='utf-8', errors='replace').splitlines()
            tail = '\n'.join(tlines[li:])[- inputs.max_telemetry_bytes:]
            parts.append('telemetry_tail:' + tail)
        break
    for aid in reversed(arts.get('apply_ids') or []):
        ap = cfg.storage.applies_dir / aid / 'telemetry.jsonl'
        if ap.is_file():
            parts.append('apply_tel:' + ap.read_text(
                encoding='utf-8', errors='replace')[- inputs.max_telemetry_bytes:])
        break
    return '\n'.join(parts)
