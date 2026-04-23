from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import subprocess
import threading
from typing import Callable

from evo.apply import GitWorkspace
from evo.apply.errors import classify
from evo.apply.runner import ApplyOptions, RoundResult, execute_apply
from evo.harness.plan import StopRequested
from evo.runtime.config import EvoConfig
from evo.service import state

log = logging.getLogger('evo.service.jobs')


class CancelToken:
    def __init__(self, jm: 'JobManager', tid: str) -> None:
        self._jm = jm
        self._tid = tid

    def requested(self) -> bool:
        s = self._jm.signals(self._tid)
        return s['stop'] or s['cancel']


class JobManager:
    def __init__(self, conn: sqlite3.Connection, config: EvoConfig,
                 *, apply_opts: ApplyOptions | None = None) -> None:
        self._conn = conn
        self._cfg = config
        self._apply_opts = apply_opts
        self._threads: dict[str, threading.Thread] = {}
        self._procs: dict[str, list[subprocess.Popen]] = {}
        self._procs_lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def config(self) -> EvoConfig:
        return self._cfg

    def signals(self, tid: str) -> dict:
        return state.signals(self._conn, tid)

    def list_recent(self, flow: str, limit: int = 50) -> list[dict]:
        return state.list_recent(self._conn, flow, limit)

    def list_rounds(self, apply_id: str) -> list[dict]:
        return state.list_rounds(self._conn, apply_id)

    def submit_run(self) -> str:
        tid = state.create_task(self._conn, 'run')
        self._spawn(tid, self._exec_run)
        return tid

    def submit_apply(self, *, report_id: str | None = None) -> str:
        report_id, parent_run_id, _ = self._resolve_report(report_id)
        tid = state.create_task(self._conn, 'apply',
                                parent_run_id=parent_run_id,
                                report_id=report_id)
        self._spawn(tid, self._exec_apply)
        return tid

    def stop(self, tid: str) -> dict:
        return state.transition(self._conn, tid, 'stop')

    def cancel(self, tid: str) -> dict:
        row = state.transition(self._conn, tid, 'cancel')
        self._kill_procs(tid)
        if row['flow'] == 'run':
            shutil.rmtree(self._cfg.storage.runs_dir / tid, ignore_errors=True)
        else:
            self._cleanup_apply(tid, drop_logs=True, drop_diffs=True)
        return row

    def cont(self, tid: str) -> dict:
        row = state.transition(self._conn, tid, 'continue')
        if row['flow'] == 'run':
            self._spawn(tid, self._exec_run)
        else:
            self._spawn(tid, self._exec_apply)
        return row

    def accept(self, tid: str) -> dict:
        return state.transition(self._conn, tid, 'accept')

    def reject(self, tid: str) -> dict:
        row = state.transition(self._conn, tid, 'reject')
        self._cleanup_apply(tid, drop_logs=False, drop_diffs=True)
        return row

    def join(self, tid: str, timeout: float = 30.0) -> None:
        t = self._threads.get(tid)
        if t is not None:
            t.join(timeout=timeout)

    # ---- internal ----

    def _spawn(self, tid: str, target: Callable[[str], None]) -> None:
        t = threading.Thread(target=target, args=(tid,), daemon=True,
                             name=f'evo-job-{tid}')
        self._threads[tid] = t
        t.start()

    def _register_proc(self, tid: str, proc: subprocess.Popen) -> None:
        with self._procs_lock:
            self._procs.setdefault(tid, []).append(proc)

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

    def _resolve_report(self, report_id: str | None) -> tuple[str, str, dict]:
        if report_id is None:
            run_row = state.latest_succeeded_run(self._conn)
            if run_row is None:
                raise state.StateError('NO_REPORT_AVAILABLE',
                                       'no succeeded run with a report')
            run_id = run_row['id']
            reports_dir = self._cfg.storage.reports_dir
            cands = sorted(reports_dir.glob(f'*{run_id[-8:]}*.json'))
            if not cands:
                cands = sorted(reports_dir.glob('*.json'),
                               key=lambda p: p.stat().st_mtime, reverse=True)
            if not cands:
                raise state.StateError('NO_REPORT_AVAILABLE',
                                       'no report file found',
                                       {'run_id': run_id})
            report_path = cands[0]
        else:
            report_path = self._cfg.storage.reports_dir / f'{report_id}.json'
            if not report_path.is_file():
                raise state.StateError('NO_REPORT_AVAILABLE',
                                       f'report {report_id} not found',
                                       {'path': str(report_path)})
        data = json.loads(report_path.read_text(encoding='utf-8'))
        rid = data.get('report_id') or report_path.stem
        meta = data.get('metadata') or {}
        parent_run_id = meta.get('run_id', '')
        return rid, parent_run_id, data

    def _cleanup_apply(self, tid: str, *, drop_logs: bool,
                       drop_diffs: bool) -> None:
        ws = GitWorkspace(self._cfg.storage.git_dir, self._cfg.chat_source)
        try:
            ws.remove_worktree(tid)
        except Exception as exc:
            log.warning('worktree cleanup failed for %s: %s', tid, exc)
        if drop_logs:
            shutil.rmtree(self._cfg.storage.applies_dir / tid, ignore_errors=True)
        if drop_diffs:
            shutil.rmtree(self._cfg.storage.diffs_dir / tid, ignore_errors=True)

    # ---- run ----

    def _exec_run(self, tid: str) -> None:
        cur = state.get(self._conn, tid)
        if cur is None:
            return
        if cur['status'] == 'queued':
            state.patch(self._conn, tid, status='running')
        token = CancelToken(self, tid)
        try:
            self._do_run_pipeline(tid, token)
        except StopRequested as exc:
            self._on_stop(tid, exc.at_step)
        except Exception as exc:
            self._on_failure(tid, exc)
        else:
            self._on_success(tid)
        finally:
            self._threads.pop(tid, None)

    def _do_run_pipeline(self, tid: str, token: CancelToken) -> None:
        from evo.harness.pipeline import RAGAnalysisPipeline
        from evo.main import default_embed_provider, default_llm_provider
        pipeline = RAGAnalysisPipeline(
            config=self._cfg,
            llm_provider=default_llm_provider(self._cfg),
            embed_provider=default_embed_provider(self._cfg),
        )
        pipeline.run(run_id=tid, cancel_token=token)

    # ---- apply ----

    def _exec_apply(self, tid: str) -> None:
        cur = state.get(self._conn, tid)
        if cur is None:
            return
        if cur['status'] == 'queued':
            state.patch(self._conn, tid, status='running')
        token = CancelToken(self, tid)
        try:
            self._do_apply(tid, token)
        except StopRequested as exc:
            self._on_stop(tid, exc.at_step)
        except Exception as exc:
            self._on_failure(tid, exc)
        finally:
            self._threads.pop(tid, None)
            with self._procs_lock:
                self._procs.pop(tid, None)

    def _do_apply(self, tid: str, token: CancelToken) -> None:
        cur = state.get(self._conn, tid)
        report_id = cur['report_id']
        report_path = self._cfg.storage.reports_dir / f'{report_id}.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        workspace = GitWorkspace(self._cfg.storage.git_dir, self._cfg.chat_source)
        opts = self._apply_opts or ApplyOptions()

        def on_round(rr: RoundResult) -> None:
            self._record_round(tid, rr)

        def on_proc(proc: subprocess.Popen) -> None:
            self._register_proc(tid, proc)

        result = execute_apply(
            apply_id=tid, report=report, config=self._cfg,
            workspace=workspace, options=opts,
            cancel_token=token, on_round=on_round, on_proc=on_proc,
        )
        state.patch(self._conn, tid,
                    base_commit=result.base_commit,
                    branch_name=result.branch_name)
        cur = state.get(self._conn, tid)
        if cur['status'] not in ('running', 'stopping'):
            return
        if result.status == 'SUCCEEDED':
            state.transition(self._conn, tid, 'finish')
        else:
            err = result.error or {}
            code = err.get('code', 'UNKNOWN')
            kind = err.get('kind') or classify(code)
            action = 'fail_permanent' if kind == 'permanent' else 'fail_transient'
            state.transition(self._conn, tid, action,
                             error_code=code, error_kind=kind)

    def _record_round(self, tid: str, rr: RoundResult) -> None:
        state.append_round(self._conn, tid, rr.index, phase='running')
        state.update_round(
            self._conn, tid, rr.index,
            phase='completed',
            commit_sha=rr.commit_sha,
            files_changed=rr.files_changed,
            test_passed=int(rr.test_passed) if rr.test_passed is not None else None,
            error_json=json.dumps(rr.error, ensure_ascii=False) if rr.error else None,
            finished_at=rr.finished_at,
        )
        state.patch(self._conn, tid, current_round=rr.index)

    # ---- transitions ----

    def _on_stop(self, tid: str, at: str | None) -> None:
        log.info('task %s stop requested at %s', tid, at)
        cur = state.get(self._conn, tid)
        if cur is None or cur['status'] != 'stopping':
            return
        kw = {'current_step': at} if cur['flow'] == 'run' else {}
        state.transition(self._conn, tid, 'ack', **kw)

    def _on_failure(self, tid: str, exc: Exception) -> None:
        log.exception('task %s failed: %s', tid, exc)
        code = getattr(exc, 'code', type(exc).__name__)
        kind = getattr(exc, 'kind', None) or classify(code)
        cur = state.get(self._conn, tid)
        if cur is None or cur['status'] not in ('running', 'stopping'):
            return
        action = 'fail_permanent' if kind == 'permanent' else 'fail_transient'
        state.transition(self._conn, tid, action, error_code=code, error_kind=kind)

    def _on_success(self, tid: str) -> None:
        cur = state.get(self._conn, tid)
        if cur is None or cur['status'] not in ('running', 'stopping'):
            return
        state.transition(self._conn, tid, 'finish')


_singleton: JobManager | None = None


def get_manager(config: EvoConfig) -> JobManager:
    global _singleton
    if _singleton is None:
        conn = state.open_db(config.storage.state_db_path)
        _singleton = JobManager(conn, config)
    return _singleton


def reset_for_tests() -> None:
    global _singleton
    _singleton = None
