from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

from evo.apply import GitWorkspace
from evo.apply.errors import classify
from evo.apply.runner import ApplyOptions, RoundResult, execute_apply
from evo.harness.plan import StopRequested
from evo.runtime.fs import load_json
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace

from .context import CancelToken, ExecCtx

log = logging.getLogger('evo.service.executors.apply')


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    is_resume = cur['status'] != 'queued'
    if not is_resume:
        ctx.report_start(tid)
    token = CancelToken(ctx, tid)
    try:
        _do_apply(ctx, tid, token, resume=is_resume)
    except StopRequested as exc:
        ctx.on_stop(tid, exc.at_step)
    except Exception as exc:
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)
        ctx.pop_procs(tid)


def _do_apply(ctx: ExecCtx, tid: str, token: CancelToken,
              *, resume: bool = False) -> None:
    cur = _store.get(ctx.store, tid)
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
        workspace=workspace, thread_id=cur.get('thread_id'),
        options=opts,
        cancel_token=token, on_round=on_round, on_proc=on_proc,
        resume=resume,
    )
    preview_dir = ctx.cfg.storage.applies_dir / tid / 'preview'
    diff_index = str(preview_dir / 'index.json') if (preview_dir / 'index.json').is_file() else None
    _store.patch(
        ctx.store, tid,
        base_commit=result.base_commit,
        branch_name=result.branch_name,
        final_commit=result.final_commit,
    )
    ctx.update_payload(tid, {
        'result': {
            'base_commit': result.base_commit,
            'branch_name': result.branch_name,
            'final_commit': result.final_commit,
            'preview_dir': str(preview_dir),
            'diff_index': diff_index,
            'round_count': len(result.rounds),
            'status': result.status,
        },
    })
    cur = _store.get(ctx.store, tid)
    if cur['status'] not in ('running', 'stopping'):
        return
    if result.status == 'SUCCEEDED':
        candidate = None
        try:
            candidate = _launch_candidate_chat(ctx, tid, cur.get('thread_id'),
                                               workspace.worktree_path(tid))
            ctx.update_payload(tid, {'result': {
                **(((_store.get(ctx.store, tid) or {}).get('payload') or {}).get('result') or {}),
                **_candidate_payload(candidate),
            }})
        except Exception as exc:
            ctx.update_payload(tid, {'result': {
                **(((_store.get(ctx.store, tid) or {}).get('payload') or {}).get('result') or {}),
                'candidate_error': str(exc),
            }})
            raise
        ctx.on_success(tid)
        c2 = _store.get(ctx.store, tid) or {}
        w2 = c2.get('thread_id')
        if w2:
            ws = ThreadWorkspace(ctx.cfg.storage.base_dir, w2)
            if candidate:
                ws.attach_artifact('chat_ids', candidate.chat_id)
            el = EventLog(ws.events_path)
            data = {'apply_id': tid}
            if candidate:
                data.update(_candidate_payload(candidate))
            el.append(f'task:{tid}', 'apply.complete', data)
    else:
        err = result.error or {}
        code = err.get('code', 'UNKNOWN')
        kind = err.get('kind') or classify(code)
        action = 'fail_permanent' if kind == 'permanent' else 'fail_transient'
        _store.transition(ctx.store, tid, action,
                          error_code=code, error_kind=kind)


def _record_round(ctx: ExecCtx, tid: str, rr: RoundResult) -> None:
    _store.append_round(ctx.store, tid, rr.index, phase='running')
    _store.update_round(
        ctx.store, tid, rr.index,
        phase='completed',
        commit_sha=rr.commit_sha,
        files_changed=rr.files_changed,
        test_passed=int(rr.test_passed) if rr.test_passed is not None else None,
        error_json=json.dumps(rr.error, ensure_ascii=False) if rr.error else None,
        finished_at=rr.finished_at,
    )
    _store.patch(ctx.store, tid, current_round=rr.index)
    c = _store.get(ctx.store, tid) or {}
    wid = c.get('thread_id')
    if wid:
        el = EventLog(ThreadWorkspace(ctx.cfg.storage.base_dir, wid).events_path)
        el.append(f'task:{tid}', 'apply.round', {'round': rr.index, 'commit_sha': rr.commit_sha})


def _launch_candidate_chat(ctx: ExecCtx, apply_id: str, thread_id: str | None,
                           worktree) -> object:
    _ensure_chat_package_alias(worktree)
    runner = ctx.chat_runner_factory()
    candidate = runner.launch(
        source_dir=worktree,
        label=f'apply-{apply_id[-6:]}',
        env={'PYTHONPATH': _candidate_pythonpath(worktree), **_chat_env()},
        owner_thread_id=thread_id,
    )
    ctx.chat_registry.register(candidate)
    return candidate


def _candidate_payload(candidate) -> dict:
    return {
        'candidate_chat_id': candidate.chat_id,
        'candidate_chat_url': candidate.base_url,
        'candidate_health_url': candidate.health_url,
        'candidate_status': candidate.status,
    }


def _chat_env() -> dict[str, str]:
    keys = (
        'LAZYRAG_MODEL_CONFIG_PATH', 'LAZYRAG_USE_INNER_MODEL',
        'LAZYRAG_MAAS_API_KEY', 'MAAS_BASE_URL', 'MAAS_MODEL_NAME',
        'LANGFUSE_HOST', 'LANGFUSE_BASE_URL', 'LANGFUSE_PUBLIC_KEY',
        'LANGFUSE_SECRET_KEY', 'LAZYLLM_TRACE_BACKEND',
        'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
        'no_proxy', 'NO_PROXY',
    )
    env = {k: v for k in keys if (v := os.getenv(k))}
    env['LAZYRAG_SKIP_STARTUP_PIPELINE'] = '1'
    return env


def _ensure_chat_package_alias(worktree) -> None:
    from pathlib import Path
    wt = Path(worktree)
    alias = wt / 'chat'
    if alias.exists():
        return
    if (wt / 'app' / 'chat.py').is_file():
        alias.symlink_to(wt, target_is_directory=True)


def _candidate_pythonpath(worktree) -> str:
    existing = os.getenv('PYTHONPATH', '')
    parts = [str(worktree), '/app', '/opt/lazyllm']
    parts.extend(p for p in existing.split(':') if p)
    return ':'.join(dict.fromkeys(parts))


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
        preview_dir = ctx.cfg.storage.applies_dir / tid / 'preview'
        shutil.rmtree(preview_dir, ignore_errors=True)


def resolve_report(ctx: ExecCtx, report_id: str | None,
                    *, thread_id: str | None = None) -> tuple[str, str, dict]:
    if report_id is not None:
        report_path = ctx.cfg.storage.reports_dir / f'{report_id}.json'
        if not report_path.is_file():
            raise _store.StateError('NO_REPORT_AVAILABLE',
                                    f'report {report_id} not found',
                                    {'path': str(report_path)})
        return _read_report(report_path)

    if thread_id:
        ws = ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id)
        for rid in reversed(ws.load_artifacts().get('run_ids') or []):
            rec = _store.get(ctx.store, rid)
            if not (rec and rec['status'] == 'succeeded' and rec.get('report_id')):
                continue
            report_path = ctx.cfg.storage.reports_dir / f"{rec['report_id']}.json"
            if report_path.is_file():
                return _read_report(report_path)
        raise _store.StateError('NO_REPORT_AVAILABLE',
                                f'thread {thread_id} has no succeeded run with report')

    run_row = _store.latest_succeeded_run(ctx.store)
    if run_row is None:
        raise _store.StateError('NO_REPORT_AVAILABLE',
                                'no succeeded run with a report')
    run_id = run_row['id']
    reports_dir = ctx.cfg.storage.reports_dir
    cands = sorted(reports_dir.glob(f'*{run_id[-8:]}*.json'))
    if not cands:
        cands = sorted(reports_dir.glob('*.json'),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        raise _store.StateError('NO_REPORT_AVAILABLE',
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
