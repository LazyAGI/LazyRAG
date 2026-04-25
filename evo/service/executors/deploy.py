from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

from evo.runtime.fs import atomic_write_json
from evo.service.core import store as _store
from evo.service.threads.workspace import EventLog, ThreadWorkspace

from .context import ExecCtx

log = logging.getLogger('evo.service.executors.deploy')


def execute(ctx: ExecCtx, tid: str) -> None:
    cur = _store.get(ctx.store, tid)
    if cur is None:
        return
    if cur['status'] == 'queued':
        ctx.report_start(tid)
    try:
        payload = cur.get('payload') or {}
        merge_id = payload.get('merge_id')
        if not merge_id:
            raise _store.StateError('DEPLOY_NO_MERGE', 'deploy requires merge_id')
        merge_row = _store.must_get(ctx.store, merge_id)
        if merge_row.get('status') != 'merged':
            raise _store.StateError('DEPLOY_MERGE_NOT_READY',
                                    f'merge {merge_id} is not merged',
                                    {'status': merge_row.get('status')})
        merge_result = (merge_row.get('payload') or {}).get('result') or {}
        merge_commit = merge_result.get('merge_commit')
        if not merge_commit:
            raise _store.StateError('DEPLOY_NO_MERGE_COMMIT',
                                    f'merge {merge_id} has no merge_commit')

        source_dir = ctx.cfg.storage.base_dir / 'deploys' / tid / 'source'
        source_dir.mkdir(parents=True, exist_ok=True)
        _checkout_merge_commit(ctx.cfg.storage.git_dir, merge_commit, source_dir)

        thread_id = cur.get('thread_id')
        role = payload.get('role') or 'production'
        runner = ctx.chat_runner_factory()
        instance = runner.launch(source_dir=source_dir, label='deploy',
                                  owner_thread_id=thread_id)
        instance.role = role
        ctx.chat_registry.register(instance)

        deployment = {
            'deploy_id': tid,
            'merge_id': merge_id,
            'merge_commit': merge_commit,
            'chat_id': instance.chat_id,
            'base_url': instance.base_url,
            'pid': instance.pid,
            'port': instance.port,
            'source_dir': str(instance.source_dir),
            'adapter': payload.get('adapter') or 'local',
            'version': payload.get('version') or 'latest',
            'role': role,
            'status': 'deployed',
            'created_at': time.time(),
        }
        deploy_dir = ctx.cfg.storage.base_dir / 'deploys' / tid
        deploy_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(deploy_dir / 'deployment.json', deployment)
        ctx.update_payload(tid, {'result': deployment})
        if thread_id:
            EventLog(ThreadWorkspace(ctx.cfg.storage.base_dir, thread_id).events_path) \
                .append(f'task:{tid}', 'deploy.complete', deployment)
        ctx.report_success(tid, 'complete_deploy')
    except Exception as exc:
        ctx.on_failure(tid, exc)
    finally:
        ctx.pop_thread(tid)


def _checkout_merge_commit(git_dir: Path, merge_commit: str, target: Path) -> None:
    bare = git_dir / 'chat.git'
    if not bare.exists():
        raise _store.StateError('DEPLOY_NO_BARE_REPO', f'bare repo not found at {bare}')
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        return
    subprocess.run(
        ['git', 'clone', '--no-checkout', str(bare), str(target)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ['git', '-C', str(target), 'checkout', merge_commit],
        capture_output=True, text=True, check=True,
    )
