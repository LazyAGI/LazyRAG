from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
import uvicorn


DEFAULT_ROOT = Path(os.environ.get('LAZYRAG_REMOTE_FS_MOCK_ROOT', '/tmp/lazyrag-remote-fs-mock'))

app = FastAPI(title='LazyRAG RemoteFS Mock')


def _json_ok(data: Any) -> dict[str, Any]:
    return {'code': 0, 'message': 'ok', 'data': data}


def _normalize_logical_path(path: str) -> str:
    raw = str(path or '').strip().strip('/')
    if not raw:
        return ''
    parts = [part for part in raw.split('/') if part not in ('', '.')]
    if any(part == '..' for part in parts):
        raise HTTPException(status_code=403, detail='path escapes configured root')
    return '/'.join(parts)


def _session_root(session_id: str) -> Path:
    sid = str(session_id or '').strip()
    if not sid:
        raise HTTPException(status_code=400, detail='session_id is required')
    if '/' in sid or sid in {'.', '..'}:
        raise HTTPException(status_code=400, detail='invalid session_id')
    return (DEFAULT_ROOT / sid).resolve()


def _resolve_target(path: str, session_id: str) -> tuple[Path, str]:
    logical_path = _normalize_logical_path(path)
    root = _session_root(session_id)
    target = (root / logical_path).resolve() if logical_path else root
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail='path escapes configured root') from exc
    return target, logical_path


def _entry_for(base: Path, item: Path) -> dict[str, Any]:
    try:
        relative_name = item.relative_to(base).as_posix()
    except ValueError:
        relative_name = item.name
    return {
        'name': relative_name,
        'size': 0 if item.is_dir() else item.stat().st_size,
        'type': 'directory' if item.is_dir() else 'file',
    }


def _wrap_http_error(exc: HTTPException) -> dict[str, Any]:
    return {'code': exc.status_code, 'message': str(exc.detail), 'data': {}}


@app.get('/remote-fs/list')
def list_remote_fs(
    path: str = Query(...),
    session_id: str = Query(...),
    detail: bool = Query(True),
):
    try:
        target, logical_path = _resolve_target(path, session_id)
        if not target.exists():
            raise HTTPException(status_code=404, detail='path does not exist')
        base = _session_root(session_id)
        if target.is_file():
            entry = _entry_for(base, target)
            return _json_ok({'entries': [entry]} if detail else {'names': [entry['name']]})

        children = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name))
        entries = [_entry_for(base, item) for item in children]
        if logical_path:
            parent = logical_path.rstrip('/')
            expected_depth = parent.count('/') + 1
            entries = [entry for entry in entries if entry['name'].count('/') == expected_depth]
        else:
            entries = [entry for entry in entries if '/' not in entry['name']]

        return _json_ok({'entries': entries} if detail else {'names': [entry['name'] for entry in entries]})
    except HTTPException as exc:
        return _wrap_http_error(exc)


@app.get('/remote-fs/info')
def info_remote_fs(
    path: str = Query(...),
    session_id: str = Query(...),
):
    try:
        target, _ = _resolve_target(path, session_id)
        if not target.exists():
            raise HTTPException(status_code=404, detail='path does not exist')
        return _json_ok(_entry_for(_session_root(session_id), target))
    except HTTPException as exc:
        return _wrap_http_error(exc)


@app.get('/remote-fs/exists')
def exists_remote_fs(
    path: str = Query(...),
    session_id: str = Query(...),
):
    try:
        target, _ = _resolve_target(path, session_id)
        return _json_ok({'exists': target.exists()})
    except HTTPException:
        return _json_ok({'exists': False})


@app.get('/remote-fs/content')
def content_remote_fs(
    path: str = Query(...),
    session_id: str = Query(...),
):
    target, _ = _resolve_target(path, session_id)
    if not target.exists():
        raise HTTPException(status_code=404, detail='path does not exist')
    if target.is_dir():
        raise HTTPException(status_code=400, detail='path points to a directory')
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type or 'application/octet-stream')


def _seed_demo_data(root: Path) -> None:
    demo_files = {
        root / 'sid-demo' / 'skills' / 'writing' / 'example' / 'SKILL.md': (
            '---\n'
            'name: example\n'
            'description: Demo writing skill for RemoteFS mock.\n'
            '---\n\n'
            '# Example Skill\n\n'
            'Use this skill to draft concise status updates.\n'
            'read_reference: references/examples/daily-update.md'
        ),
        root / 'sid-demo' / 'skills' / 'writing' / 'example' / 'references' / 'style-guide.md': (
            '# Style Guide\n\n'
            '- Lead with the conclusion.\n'
            '- Keep sentences short.\n'
        ),
        root / 'sid-demo' / 'skills' / 'writing' / 'example' / 'references' / 'examples' / 'daily-update.md': (
            '# Daily Update\n\n'
            'Completed API integration and validated the smoke test.\n'
        ),
        root / 'sid-demo' / 'skills' / 'ops' / 'deploy-checklist' / 'SKILL.md': (
            '---\n'
            'name: deploy-checklist\n'
            'description: Demo ops skill for RemoteFS mock.\n'
            '---\n\n'
            '# Deploy Checklist\n\n'
            'Verify migrations, rollout order, and rollback commands.\n'
        ),
        root / 'sid-demo' / 'skills' / 'ops' / 'deploy-checklist' / 'references' / 'rollback.md': (
            '# Rollback\n\n'
            'Run the rollback job and confirm service health recovers.\n'
        ),
    }

    for path, content in demo_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def main() -> None:
    global DEFAULT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--port', type=int, default=18080)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--seed-demo-data', action='store_true')
    args = parser.parse_args()

    DEFAULT_ROOT = args.root.resolve()
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)

    if args.seed_demo_data:
        _seed_demo_data(DEFAULT_ROOT)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
