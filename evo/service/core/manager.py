from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from evo.abtest import VerdictPolicy
from evo.apply.errors import classify
from evo.apply.runner import ApplyOptions
from evo.chat_runner import ChatRegistry, ChatRunner, SubprocessChatRunner
from evo.runtime.config import EvoConfig
from evo.service.core import store
from evo.service.executors import EXECUTORS, ExecCtx
from evo.service.executors import apply as apply_exec
from evo.service.threads.workspace import EventLog, ThreadWorkspace

log = logging.getLogger('evo.service.core.manager')


class TaskRegistry:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._procs: dict[str, list[subprocess.Popen]] = {}
        self._procs_lock = threading.Lock()
        self._abtest_policy: dict[str, VerdictPolicy] = {}

    def register_thread(self, tid: str, t: threading.Thread) -> None:
        self._threads[tid] = t

    def pop_thread(self, tid: str) -> None:
        self._threads.pop(tid, None)

    def register_proc(self, tid: str, proc: subprocess.Popen) -> None:
        with self._procs_lock:
            self._procs.setdefault(tid, []).append(proc)

    def pop_procs(self, tid: str) -> None:
        with self._procs_lock:
            self._procs.pop(tid, None)

    def kill_procs(self, tid: str) -> None:
        with self._procs_lock:
            procs = self._procs.pop(tid, [])
        for p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except ProcessLookupError:
                    pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    p.kill()
                except ProcessLookupError:
                    pass

    def get_thread(self, tid: str) -> threading.Thread | None:
        return self._threads.get(tid)

    def set_abtest_policy(self, tid: str, policy: VerdictPolicy) -> None:
        self._abtest_policy[tid] = policy

    def pop_abtest_policy(self, tid: str) -> None:
        self._abtest_policy.pop(tid, None)

    def get_abtest_policy(self, tid: str) -> VerdictPolicy:
        return self._abtest_policy.get(tid) or VerdictPolicy()


class ArtifactBinder:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def attach(self, thread_id: str | None, kind: str, value: str) -> None:
        if not thread_id:
            return
        ThreadWorkspace(self._base_dir, thread_id).attach_artifact(kind, value)

    def event_log(self, thread_id: str | None) -> EventLog | None:
        if not thread_id:
            return None
        ws = ThreadWorkspace(self._base_dir, thread_id)
        return EventLog(ws.events_path)


class JobManager:
    def __init__(self, st: store.FsStateStore, config: EvoConfig,
                 *, apply_opts: ApplyOptions | None = None,
                 chat_runner: ChatRunner | None = None,
                 chat_registry: ChatRegistry | None = None) -> None:
        self._store = st
        self._cfg = config
        self._apply_opts = apply_opts
        self._chat_runner = chat_runner or _default_chat_runner(config)
        self._chat_registry = chat_registry or ChatRegistry(config.storage.base_dir)
        self._registry = TaskRegistry()
        self._binder = ArtifactBinder(config.storage.base_dir)

    @property
    def store(self) -> store.FsStateStore:
        return self._store

    @property
    def conn(self) -> store.FsStateStore:
        return self._store

    @property
    def config(self) -> EvoConfig:
        return self._cfg

    @property
    def chat_registry(self) -> ChatRegistry:
        return self._chat_registry

    def signals(self, tid: str) -> dict:
        return store.signals(self._store, tid)

    def list_recent(self, flow: str, limit: int = 50) -> list[dict]:
        return store.list_recent(self._store, flow, limit)

    def list_rounds(self, apply_id: str) -> list[dict]:
        return store.list_rounds(self._store, apply_id)

    def apply_commits_for_thread(self, thread_id: str) -> list[dict]:
        rows = store.list_flow_tasks_by_thread(self._store, 'apply', thread_id)
        out: list[dict] = []
        for row in rows:
            aid = row['id']
            rounds = store.list_rounds(self._store, aid)
            commits = []
            for r in rounds:
                sha = r.get('commit_sha')
                if not sha:
                    continue
                commits.append({
                    'round': r.get('round'),
                    'commit_sha': sha,
                    'test_passed': r.get('test_passed'),
                    'files_changed': r.get('files_changed'),
                })
            out.append({
                'apply_id': aid,
                'status': row.get('status'),
                'thread_id': row.get('thread_id'),
                'branch_name': row.get('branch_name'),
                'base_commit': row.get('base_commit'),
                'final_commit': row.get('final_commit'),
                'commits': commits,
                'rounds': rounds,
            })
        return out

    def submit_run(self, *, thread_id: str | None = None,
                   eval_id: str | None = None,
                   badcase_limit: int | None = None,
                   score_field: str | None = None) -> str:
        eid = eval_id or self._latest_thread_eval(thread_id)
        payload: dict[str, Any] = {}
        if eid:
            payload['eval_id'] = eid
        if badcase_limit is not None:
            payload['badcase_limit'] = badcase_limit
        if score_field:
            payload['score_field'] = score_field
        tid = store.create_task(self._store, 'run', thread_id=thread_id,
                                payload=payload)
        self._binder.attach(thread_id, 'run_ids', tid)
        self._spawn(tid, 'run')
        return tid

    def submit_apply(self, *, report_id: str | None = None,
                     thread_id: str | None = None) -> str:
        rid, parent_run_id, _ = apply_exec.resolve_report(
            self._make_ctx(), report_id, thread_id=thread_id)
        existing = _matching_apply(self._store, thread_id, rid)
        if existing:
            return existing['id']
        tid = store.create_task(self._store, 'apply',
                                parent_run_id=parent_run_id,
                                report_id=rid, thread_id=thread_id)
        self._binder.attach(thread_id, 'apply_ids', tid)
        self._spawn(tid, 'apply')
        return tid

    def submit_eval(self, *, thread_id: str,
                     eval_id: str | None = None,
                     dataset_id: str | None = None,
                     target_chat_url: str | None = None,
                     options: dict | None = None) -> str:
        if not eval_id and not dataset_id:
            raise store.StateError('EVAL_NO_TARGET',
                                    'need eval_id or dataset_id')
        payload: dict[str, Any] = {}
        if eval_id:
            payload['eval_id'] = eval_id
        if dataset_id:
            payload['dataset_id'] = dataset_id
        if target_chat_url:
            payload['target_chat_url'] = target_chat_url
        if options:
            payload['eval_options'] = options
        tid = store.create_task(self._store, 'eval',
                                thread_id=thread_id, payload=payload)
        if eval_id:
            self._binder.attach(thread_id, 'eval_ids', eval_id)
        self._spawn(tid, 'eval')
        return tid

    def submit_abtest(self, *, thread_id: str, apply_id: str,
                      baseline_eval_id: str, dataset_id: str,
                      apply_worktree: Path | None = None,
                      target_chat_url: str | None = None,
                      candidate_chat_id: str | None = None,
                      eval_options: dict | None = None,
                      policy: VerdictPolicy | dict | None = None) -> str:
        apply_row = store.must_get(self._store, apply_id)
        _require_apply_ready_for_abtest(self._store, apply_row)
        existing = _matching_abtest(self._store, thread_id, apply_id,
                                    baseline_eval_id, dataset_id)
        if existing:
            return existing['id']
        worktree = apply_worktree or apply_exec.resolve_worktree(
            self._make_ctx(), apply_id)
        apply_result = (apply_row.get('payload') or {}).get('result') or {}
        verdict_policy = _coerce_policy(policy)
        payload = {
            'apply_id': apply_id,
            'baseline_eval_id': baseline_eval_id,
            'dataset_id': dataset_id,
            'apply_worktree': str(worktree),
            'eval_options': eval_options or {},
            'policy': verdict_policy.__dict__,
        }
        cid = candidate_chat_id or apply_result.get('candidate_chat_id')
        if cid:
            payload['candidate_chat_id'] = cid
        url = target_chat_url or apply_result.get('candidate_chat_url')
        if url:
            payload['target_chat_url'] = url
        tid = store.create_task(self._store, 'abtest',
                                thread_id=thread_id, payload=payload)
        self._binder.attach(thread_id, 'abtest_ids', tid)
        self._registry.set_abtest_policy(tid, verdict_policy)
        self._spawn(tid, 'abtest')
        return tid

    def submit_dataset_gen(self, *, thread_id: str | None = None,
                           kb_id: str, algo_id: str | None = None,
                           eval_name: str | None = None,
                           num_cases: int | None = None) -> str:
        payload: dict[str, Any] = {'kb_id': kb_id}
        if algo_id:
            payload['algo_id'] = algo_id
        if eval_name:
            payload['eval_name'] = eval_name
        if num_cases is not None:
            payload['num_cases'] = num_cases
        tid = store.create_task(self._store, 'dataset_gen',
                                thread_id=thread_id, payload=payload)
        if eval_name:
            self._binder.attach(thread_id, 'dataset_ids', eval_name)
        self._spawn(tid, 'dataset_gen')
        return tid

    def stop(self, tid: str) -> dict:
        return store.transition(self._store, tid, 'stop')

    def cancel(self, tid: str) -> dict:
        row = store.transition(self._store, tid, 'cancel')
        self._registry.kill_procs(tid)
        if row['flow'] == 'run':
            shutil.rmtree(self._cfg.storage.runs_dir / tid, ignore_errors=True)
        elif row['flow'] == 'apply':
            self._stop_apply_candidate(row)
            apply_exec.cleanup(self._make_ctx(), tid,
                                drop_logs=True, drop_diffs=True)
        return row

    def cont(self, tid: str) -> dict:
        row = store.get(self._store, tid)
        if row is None:
            raise store.StateError('TASK_NOT_FOUND', f'task {tid} not found')
        flow = row['flow']
        if flow not in ('dataset_gen', 'eval', 'run', 'apply', 'abtest'):
            raise store.StateError('UNSUPPORTED_CONTINUE',
                                    f'flow {flow} does not support continue')
        row = store.transition(self._store, tid, 'continue')
        self._spawn(tid, flow)
        return row

    def accept(self, tid: str, auto_next: str | bool = 'none') -> dict:
        row = store.transition(self._store, tid, 'accept')
        payload = dict(row.get('payload') or {})
        result = dict(payload.get('result') or {})
        final_commit = row.get('final_commit') or result.get('final_commit')
        if final_commit:
            result['accepted_commit'] = final_commit
            result['accepted_at'] = time.time()
            payload['result'] = result
            store.patch(self._store, tid, payload=payload)
            row = store.get(self._store, tid) or row
            thread_id = row.get('thread_id')
            if thread_id:
                self._binder.attach(thread_id, 'apply_commit_ids', final_commit)
                elog = self._binder.event_log(thread_id)
                if elog:
                    elog.append(f'task:{tid}', 'apply.accepted',
                                {'apply_id': tid, 'commit': final_commit})
        return row

    def reject(self, tid: str) -> dict:
        row = store.transition(self._store, tid, 'reject')
        self._stop_apply_candidate(row)
        apply_exec.cleanup(self._make_ctx(), tid,
                            drop_logs=False, drop_diffs=True)
        return row

    def cancel_all(self, flow: str, *, thread_id: str | None = None) -> list[dict]:
        scope = 'thread' if thread_id else 'global'
        active = store.list_active(self._store, flow, scope=scope,
                                    thread_id=thread_id)
        ids = [a['id'] for a in active]
        return store.transition_many(self._store, ids, 'cancel')

    def stop_all(self, flow: str, *, thread_id: str | None = None) -> list[dict]:
        scope = 'thread' if thread_id else 'global'
        active = store.list_active(self._store, flow, scope=scope,
                                    thread_id=thread_id)
        ids = [a['id'] for a in active]
        return store.transition_many(self._store, ids, 'stop')

    def join(self, tid: str, timeout: float = 30.0) -> None:
        t = self._registry.get_thread(tid)
        if t is not None:
            t.join(timeout=timeout)

    def _spawn(self, tid: str, flow: str) -> None:
        target = EXECUTORS[flow]
        ctx = self._make_ctx()
        t = threading.Thread(target=target, args=(ctx, tid), daemon=True,
                              name=f'evo-job-{tid}')
        self._registry.register_thread(tid, t)
        t.start()

    def _make_ctx(self) -> ExecCtx:
        return ExecCtx(
            store=self._store, cfg=self._cfg,
            is_cancelled=self._is_cancelled,
            register_proc=self._registry.register_proc,
            chat_runner_factory=lambda: self._chat_runner,
            chat_registry=self._chat_registry,
            apply_opts=self._apply_opts,
            abtest_policy=self._registry._abtest_policy,
            on_stop=self._on_stop,
            on_failure=self._on_failure,
            on_success=self._on_success,
            pop_thread=self._registry.pop_thread,
            pop_procs=self._registry.pop_procs,
        )

    def _is_cancelled(self, tid: str) -> bool:
        s = store.signals(self._store, tid)
        return s['stop'] or s['cancel']

    def _stop_apply_candidate(self, row: dict) -> None:
        result = ((row.get('payload') or {}).get('result') or {})
        chat_id = result.get('candidate_chat_id')
        if not chat_id:
            return
        try:
            self._chat_runner.stop(chat_id)
        except Exception:
            inst = self._chat_registry.get(chat_id)
            if inst and inst.pid:
                try:
                    os.kill(inst.pid, 15)
                except OSError:
                    pass
        self._chat_registry.purge(chat_id)

    def _latest_thread_eval(self, thread_id: str | None) -> str | None:
        if not thread_id:
            return None
        ws = ThreadWorkspace(self._cfg.storage.base_dir, thread_id)
        evals = (ws.load_artifacts() or {}).get('eval_ids') or []
        return evals[-1] if evals else None

    def _on_stop(self, tid: str, at: str | None) -> None:
        log.info('task %s stop requested at %s', tid, at)
        cur = store.get(self._store, tid)
        if cur is None or cur['status'] != 'stopping':
            return
        kw = {'current_step': at} if cur['flow'] == 'run' else {}
        store.transition(self._store, tid, 'ack', **kw)

    def _on_failure(self, tid: str, exc: Exception) -> None:
        log.exception('task %s failed: %s', tid, exc)
        code = getattr(exc, 'code', type(exc).__name__)
        kind = getattr(exc, 'kind', None) or classify(code)
        cur = store.get(self._store, tid)
        if cur is None or cur['status'] not in ('running', 'stopping'):
            return
        action = 'fail_permanent' if kind == 'permanent' else 'fail_transient'
        store.transition(self._store, tid, action,
                          error_code=code, error_kind=kind)

    def _on_success(self, tid: str, final_action: str = 'finish') -> None:
        cur = store.get(self._store, tid)
        if cur is None:
            return
        status = cur['status']
        if status in ('running', 'stopping'):
            row = store.transition(self._store, tid, final_action)

def build_manager(config: EvoConfig) -> JobManager:
    st = store.open_db(config.storage.state_db_path)
    return JobManager(st, config)


def _default_chat_runner(cfg: EvoConfig) -> ChatRunner:
    return SubprocessChatRunner(
        log_dir=cfg.storage.base_dir / 'state' / 'chats',
        health_path=os.getenv('EVO_CANDIDATE_CHAT_HEALTH_PATH', '/health'),
        startup_timeout_s=float(os.getenv('EVO_CANDIDATE_CHAT_STARTUP_TIMEOUT_S', '120')),
    )


def _coerce_policy(policy: VerdictPolicy | dict | None) -> VerdictPolicy:
    if policy is None:
        return VerdictPolicy()
    if isinstance(policy, VerdictPolicy):
        return policy
    data = dict(policy)
    if 'guard_metrics' in data and isinstance(data['guard_metrics'], list):
        data['guard_metrics'] = tuple(data['guard_metrics'])
    return VerdictPolicy(**data)


def _matching_apply(st: store.FsStateStore, thread_id: str | None,
                    report_id: str) -> dict | None:
    rows = (store.list_flow_tasks_by_thread(st, 'apply', thread_id)
            if thread_id else store.list_recent(st, 'apply', 100))
    reusable = {'queued', 'running', 'stopping', 'paused',
                'failed_transient', 'succeeded', 'accepted'}
    for row in reversed(rows):
        if row.get('report_id') == report_id and row.get('status') in reusable:
            return row
    return None


def _matching_abtest(st: store.FsStateStore, thread_id: str, apply_id: str,
                     baseline_eval_id: str, dataset_id: str) -> dict | None:
    rows = store.list_flow_tasks_by_thread(st, 'abtest', thread_id)
    reusable = {'queued', 'running', 'stopping', 'paused',
                'failed_transient', 'succeeded'}
    for row in reversed(rows):
        payload = row.get('payload') or {}
        if (
            row.get('status') in reusable
            and payload.get('apply_id') == apply_id
            and payload.get('baseline_eval_id') == baseline_eval_id
            and payload.get('dataset_id') == dataset_id
        ):
            return row
    return None


def _require_apply_ready_for_abtest(st: store.FsStateStore,
                                    apply_row: dict) -> None:
    payload = apply_row.get('payload') or {}
    result = payload.get('result') or {}
    status = apply_row.get('status')
    if status not in {'succeeded', 'accepted'}:
        raise store.StateError(
            'APPLY_NOT_READY_FOR_ABTEST',
            f'apply {apply_row.get("id")} must finish before abtest',
            {'status': status},
        )
    final_commit = apply_row.get('final_commit') or result.get('final_commit')
    if result.get('status') != 'SUCCEEDED' or not final_commit:
        raise store.StateError(
            'APPLY_NOT_READY_FOR_ABTEST',
            f'apply {apply_row.get("id")} has no successful final commit',
            {'result_status': result.get('status'), 'final_commit': final_commit},
        )
    rounds = store.list_rounds(st, apply_row['id'])
    if not rounds or rounds[-1].get('test_passed') != 1:
        raise store.StateError(
            'APPLY_TESTS_NOT_PASSED',
            f'apply {apply_row.get("id")} final round did not pass tests',
            {'round_count': len(rounds)},
        )
