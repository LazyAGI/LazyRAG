from __future__ import annotations

import json
import logging
import shutil
import subprocess

from evo.apply import GitWorkspace
from evo.apply.errors import classify
from evo.apply.runner import ApplyOptions, RoundResult, execute_apply
from evo.harness.plan import StopRequested
from evo.runtime.fs import load_json
from evo.service import state
from evo.service.thread_workspace import ThreadWorkspace

from .context import CancelToken, ExecCtx

log = logging.getLogger('evo.service.executors.apply')


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = state.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        state.patch(ctx.store, tid, status='running')
    token = CancelToken(ctx, tid)
    try:
        _do_apply(ctx, tid, token)
    except StopRequested as exc:
        ctx.on_stop(tid, exc.at_step)
    except Exception as exc:
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)
        ctx.pop_procs(tid)


def _do_apply(ctx: ExecCtx, tid: str, token: CancelToken) -> None:
    cur = state.get(ctx.store, tid)
    report_id = cur['report_id']
    report = load_json(ctx.cfg.storage.reports_dir / f'{report_id}.json')
    workspace = GitWorkspace(ctx.cfg.storage.git_dir, ctx.cfg.chat_source)
    opts = ctx.apply_opts or ApplyOptions()

    def on_round(rr: RoundResult) -> None:
        _record_round(ctx, tid, rr)

    def on_proc(proc: subprocess.Popen) -> None:
        ctx.register_proc(tid, proc)

    result = execute_apply(
        apply_id=tid, report=report, config=ctx.cfg,
        workspace=workspace, options=opts,
        cancel_token=token, on_round=on_round, on_proc=on_proc,
    )
    state.patch(ctx.store, tid,
                base_commit=result.base_commit,
                branch_name=result.branch_name)
    cur = state.get(ctx.store, tid)
    if cur['status'] not in ('running', 'stopping'):
        return
    if result.status == 'SUCCEEDED':
        state.transition(ctx.store, tid, 'finish')
    else:
        err = result.error or {}
        code = err.get('code', 'UNKNOWN')
        kind = err.get('kind') or classify(code)
        action = 'fail_permanent' if kind == 'permanent' else 'fail_transient'
        state.transition(ctx.store, tid, action,
                          error_code=code, error_kind=kind)


def _record_round(ctx: ExecCtx, tid: str, rr: RoundResult) -> None:
    state.append_round(ctx.store, tid, rr.index, phase='running')
    state.update_round(
        ctx.store, tid, rr.index,
        phase='completed',
        commit_sha=rr.commit_sha,
        files_changed=rr.files_changed,
        test_passed=int(rr.test_passed) if rr.test_passed is not None else None,
        error_json=json.dumps(rr.error, ensure_ascii=False) if rr.error else None,
        finished_at=rr.finished_at,
    )
    state.patch(ctx.store, tid, current_round=rr.index)


def cleanup(ctx: ExecCtx, tid: str, *, drop_logs: bool, drop_diffs: bool) -> None:
    ws = GitWorkspace(ctx.cfg.storage.git_dir, ctx.cfg.chat_source)
    try:
        ws.remove_worktree(tid)
    except Exception as exc:
        log.warning('worktree cleanup failed for %s: %s', tid, exc)
    if drop_logs:
        shutil.rmtree(ctx.cfg.storage.applies_dir / tid, ignore_errors=True)
    if drop_diffs:
        shutil.rmtree(ctx.cfg.storage.diffs_dir / tid, ignore_errors=True)


def resolve_report(ctx: ExecCtx, report_id: str | None,
                    *, thread_id: str | None = None) -> tuple[str, str, dict]:
    if report_id is not None:
        report_path = ctx.cfg.storage.reports_dir / f'{report_id}.json'
        if not report_path.is_file():
            raise state.StateError('NO_REPORT_AVAILABLE',
                                    f'report {report_id} not found',
                                    {'path': str(report_path)})
        return _read_report(report_path)

    if thread_id:
        ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
        for rid in reversed(ws.load_artifacts().get('run_ids') or []):
            rec = state.get(ctx.store, rid)
            if not (rec and rec['status'] == 'succeeded' and rec.get('report_id')):
                continue
            report_path = ctx.cfg.storage.reports_dir / f"{rec['report_id']}.json"
            if report_path.is_file():
                return _read_report(report_path)
        raise state.StateError('NO_REPORT_AVAILABLE',
                                f'thread {thread_id} has no succeeded run with report')

    run_row = state.latest_succeeded_run(ctx.store)
    if run_row is None:
        raise state.StateError('NO_REPORT_AVAILABLE',
                                'no succeeded run with a report')
    run_id = run_row['id']
    reports_dir = ctx.cfg.storage.reports_dir
    cands = sorted(reports_dir.glob(f'*{run_id[-8:]}*.json'))
    if not cands:
        cands = sorted(reports_dir.glob('*.json'),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        raise state.StateError('NO_REPORT_AVAILABLE',
                                'no report file found', {'run_id': run_id})
    return _read_report(cands[0])


def _read_report(report_path) -> tuple[str, str, dict]:
    data = load_json(report_path)
    rid = data.get('report_id') or report_path.stem
    parent_run_id = (data.get('metadata') or {}).get('run_id', '')
    return rid, parent_run_id, data


def resolve_worktree(ctx: ExecCtx, apply_id: str):
    return GitWorkspace(ctx.cfg.storage.git_dir,
                         ctx.cfg.chat_source).worktree_path(apply_id)
