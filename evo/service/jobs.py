from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from evo.abtest import VerdictPolicy
from evo.apply.errors import classify
from evo.apply.runner import ApplyOptions
from evo.chat_runner import ChatRegistry, ChatRunner, SubprocessChatRunner
from evo.providers import (
    EvalProvider, TraceProvider, get_eval_provider, get_trace_provider,
)
from evo.runtime.config import EvoConfig
from evo.service import state
from evo.service.executors import EXECUTORS, ExecCtx, apply as apply_exec
from evo.service.thread_workspace import EventLog, ThreadWorkspace

log = logging.getLogger('evo.service.jobs')


class JobManager:
    def __init__(self, store: state.FsStateStore, config: EvoConfig,
                 *, apply_opts: ApplyOptions | None = None,
                 eval_provider: EvalProvider | None = None,
                 trace_provider: TraceProvider | None = None,
                 chat_runner: ChatRunner | None = None,
                 chat_registry: ChatRegistry | None = None) -> None:
        self._store = store
        self._cfg = config
        self._apply_opts = apply_opts
        self._eval_provider = eval_provider
        self._trace_provider = trace_provider
        self._chat_runner = chat_runner
        self._chat_registry = chat_registry or ChatRegistry(config.storage.base_dir)
        self._threads: dict[str, threading.Thread] = {}
        self._procs: dict[str, list[subprocess.Popen]] = {}
        self._procs_lock = threading.Lock()
        self._abtest_policy: dict[str, VerdictPolicy] = {}

    @property
    def store(self) -> state.FsStateStore:
        return self._store

    @property
    def conn(self) -> state.FsStateStore:
        return self._store

    @property
    def config(self) -> EvoConfig:
        return self._cfg

    @property
    def chat_registry(self) -> ChatRegistry:
        return self._chat_registry

    def signals(self, tid: str) -> dict:
        return state.signals(self._store, tid)

    def list_recent(self, flow: str, limit: int = 50) -> list[dict]:
        return state.list_recent(self._store, flow, limit)

    def list_rounds(self, apply_id: str) -> list[dict]:
        return state.list_rounds(self._store, apply_id)

    def apply_commits_for_thread(self, thread_id: str) -> list[dict]:
        rows = state.list_flow_tasks_by_thread(self._store, 'apply', thread_id)
        out: list[dict] = []
        for row in rows:
            aid = row['id']
            rounds = state.list_rounds(self._store, aid)
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


    # ---- submission ----------------------------------------------------------

    def submit_run(self, *, thread_id: str | None = None,
                   eval_id: str | None = None,
                   badcase_limit: int | None = None,
                   score_field: str | None = None) -> str:
        eid = eval_id or self._latest_thread_eval(thread_id)
        payload: dict[str, Any] = {}
        if eid: payload['eval_id'] = eid
        if badcase_limit is not None: payload['badcase_limit'] = badcase_limit
        if score_field: payload['score_field'] = score_field
        tid = state.create_task(self._store, 'run', thread_id=thread_id,
                                payload=payload)
        self._attach_thread_artifact(thread_id, 'run_ids', tid)
        self._spawn(tid, 'run')
        return tid

    def submit_apply(self, *, report_id: str | None = None,
                     thread_id: str | None = None) -> str:
        rid, parent_run_id, _ = apply_exec.resolve_report(
            self._make_ctx(), report_id, thread_id=thread_id)
        tid = state.create_task(self._store, 'apply',
                                parent_run_id=parent_run_id,
                                report_id=rid, thread_id=thread_id)
        self._attach_thread_artifact(thread_id, 'apply_ids', tid)
        self._spawn(tid, 'apply')
        return tid

    def submit_eval(self, *, thread_id: str,
                     eval_id: str | None = None,
                     dataset_id: str | None = None,
                     target_chat_url: str | None = None,
                     options: dict | None = None) -> str:
        if not eval_id and not dataset_id:
            raise state.StateError('EVAL_NO_TARGET',
                                    'need eval_id or dataset_id')
        payload: dict[str, Any] = {}
        if eval_id: payload['eval_id'] = eval_id
        if dataset_id: payload['dataset_id'] = dataset_id
        if target_chat_url: payload['target_chat_url'] = target_chat_url
        if options: payload['eval_options'] = options
        tid = state.create_task(self._store, 'eval',
                                thread_id=thread_id, payload=payload)
        if eval_id:
            self._attach_thread_artifact(thread_id, 'eval_ids', eval_id)
        self._spawn(tid, 'eval')
        return tid

    def submit_abtest(self, *, thread_id: str, apply_id: str,
                      baseline_eval_id: str, dataset_id: str,
                      apply_worktree: Path | None = None,
                      eval_options: dict | None = None,
                      policy: VerdictPolicy | None = None) -> str:
        worktree = apply_worktree or apply_exec.resolve_worktree(
            self._make_ctx(), apply_id)
        payload = {
            'apply_id': apply_id,
            'baseline_eval_id': baseline_eval_id,
            'dataset_id': dataset_id,
            'apply_worktree': str(worktree),
            'eval_options': eval_options or {},
        }
        tid = state.create_task(self._store, 'abtest',
                                thread_id=thread_id, payload=payload)
        self._attach_thread_artifact(thread_id, 'abtest_ids', tid)
        self._abtest_policy[tid] = policy or VerdictPolicy()
        self._spawn(tid, 'abtest')
        return tid

    # ---- transitions --------------------------------------------------------

    def stop(self, tid: str) -> dict:
        return state.transition(self._store, tid, 'stop')

    def cancel(self, tid: str) -> dict:
        row = state.transition(self._store, tid, 'cancel')
        self._kill_procs(tid)
        if row['flow'] == 'run':
            shutil.rmtree(self._cfg.storage.runs_dir / tid, ignore_errors=True)
        elif row['flow'] == 'apply':
            apply_exec.cleanup(self._make_ctx(), tid,
                                drop_logs=True, drop_diffs=True)
        return row

    def cont(self, tid: str) -> dict:
        row = state.transition(self._store, tid, 'continue')
        flow = row['flow']
        target = EXECUTORS.get(flow)
        if target is None:
            raise state.StateError('UNSUPPORTED_FLOW',
                                    f'cannot continue flow {flow}')
        self._spawn(tid, flow)
        return row

    def accept(self, tid: str) -> dict:
        return state.transition(self._store, tid, 'accept')

    def reject(self, tid: str) -> dict:
        row = state.transition(self._store, tid, 'reject')
        apply_exec.cleanup(self._make_ctx(), tid,
                            drop_logs=False, drop_diffs=True)
        return row

    def join(self, tid: str, timeout: float = 30.0) -> None:
        t = self._threads.get(tid)
        if t is not None:
            t.join(timeout=timeout)

    # ---- internal -----------------------------------------------------------

    def _spawn(self, tid: str, flow: str) -> None:
        target = EXECUTORS[flow]
        ctx = self._make_ctx()
        t = threading.Thread(target=target, args=(ctx, tid), daemon=True,
                              name=f'evo-job-{tid}')
        self._threads[tid] = t
        t.start()

    def _make_ctx(self) -> ExecCtx:
        return ExecCtx(
            store=self._store, cfg=self._cfg,
            is_cancelled=self._is_cancelled,
            register_proc=self._register_proc,
            eval_provider_factory=lambda: self._eval_provider or get_eval_provider(),
            trace_provider_factory=lambda: self._trace_provider or get_trace_provider(),
            chat_runner_factory=lambda: self._chat_runner or _default_chat_runner(self._cfg),
            chat_registry=self._chat_registry,
            apply_opts=self._apply_opts,
            abtest_policy=self._abtest_policy,
            on_stop=self._on_stop,
            on_failure=self._on_failure,
            on_success=self._on_success,
            pop_thread=self._pop_thread,
            pop_procs=self._pop_procs,
        )

    def _is_cancelled(self, tid: str) -> bool:
        s = state.signals(self._store, tid)
        return s['stop'] or s['cancel']

    def _register_proc(self, tid: str, proc: subprocess.Popen) -> None:
        with self._procs_lock:
            self._procs.setdefault(tid, []).append(proc)

    def _pop_thread(self, tid: str) -> None:
        self._threads.pop(tid, None)

    def _pop_procs(self, tid: str) -> None:
        with self._procs_lock:
            self._procs.pop(tid, None)

    def _kill_procs(self, tid: str) -> None:
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

    def _latest_thread_eval(self, thread_id: str | None) -> str | None:
        if not thread_id:
            return None
        ws = ThreadWorkspace(self._cfg.storage.base_dir, thread_id)
        evals = (ws.load_artifacts() or {}).get('eval_ids') or []
        return evals[-1] if evals else None

    def _attach_thread_artifact(self, thread_id: str | None,
                                kind: str, value: str) -> None:
        if not thread_id:
            return
        ThreadWorkspace(self._cfg.storage.base_dir, thread_id) \
            .attach_artifact(kind, value)

    def _thread_log(self, thread_id: str | None) -> EventLog | None:
        if not thread_id:
            return None
        ws = ThreadWorkspace(self._cfg.storage.base_dir, thread_id)
        return EventLog(ws.events_path)

    # ---- transitions called by executors ------------------------------------

    def _on_stop(self, tid: str, at: str | None) -> None:
        log.info('task %s stop requested at %s', tid, at)
        cur = state.get(self._store, tid)
        if cur is None or cur['status'] != 'stopping':
            return
        kw = {'current_step': at} if cur['flow'] == 'run' else {}
        state.transition(self._store, tid, 'ack', **kw)

    def _on_failure(self, tid: str, exc: Exception) -> None:
        log.exception('task %s failed: %s', tid, exc)
        code = getattr(exc, 'code', type(exc).__name__)
        kind = getattr(exc, 'kind', None) or classify(code)
        cur = state.get(self._store, tid)
        if cur is None or cur['status'] not in ('running', 'stopping'):
            return
        action = 'fail_permanent' if kind == 'permanent' else 'fail_transient'
        state.transition(self._store, tid, action,
                          error_code=code, error_kind=kind)

    def _on_success(self, tid: str) -> None:
        cur = state.get(self._store, tid)
        if cur is None or cur['status'] not in ('running', 'stopping'):
            return
        state.transition(self._store, tid, 'finish')


_singleton: JobManager | None = None
_singleton_lock = threading.Lock()


def get_manager(config: EvoConfig) -> JobManager:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                store = state.open_db(config.storage.state_db_path)
                _singleton = JobManager(store, config)
    return _singleton


def reset_for_tests() -> None:
    global _singleton
    _singleton = None


def _default_chat_runner(cfg: EvoConfig) -> ChatRunner:
    return SubprocessChatRunner(log_dir=cfg.storage.base_dir / 'state' / 'chats')
