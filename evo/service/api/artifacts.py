from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from evo.runtime.config import EvoConfig
from evo.service.core import store as _store

_NAME_RE = re.compile(r'^[\w\-.]+\.(json|md|diff|bundle\.json)$')


def _safe_path(base: str, *parts: str) -> str:
    target = Path(base)
    for p in parts:
        target = target / p
    resolved = target.resolve()
    base_resolved = Path(base).resolve()
    if not resolved.is_relative_to(base_resolved):
        raise HTTPException(400, 'path traversal detected')
    return str(resolved)


def build_artifacts_router(cfg: EvoConfig) -> APIRouter:
    router = APIRouter(prefix='/v1/evo', tags=['artifacts'])

    @router.get('/reports/{report_id}/content')
    def report_content(report_id: str, fmt: str = 'json') -> FileResponse:
        suffix = '.json' if fmt == 'json' else '.md'
        if not _NAME_RE.match(f'{report_id}{suffix}'):
            raise HTTPException(400, 'invalid report filename')
        path = cfg.storage.reports_dir / f'{report_id}{suffix}'
        if not path.is_file():
            raise HTTPException(404, 'report not found')
        return FileResponse(path)

    @router.get('/diffs/{apply_id}/{filename}')
    def diff_file(apply_id: str, filename: str) -> FileResponse:
        if not _NAME_RE.match(filename) or not filename.endswith('.diff'):
            raise HTTPException(400, 'invalid diff filename')
        path = Path(_safe_path(str(cfg.storage.diffs_dir), apply_id, filename))
        if not path.is_file():
            raise HTTPException(404, 'diff not found')
        return FileResponse(path, media_type='text/x-diff')

    @router.get('/{flow}s/{tid}/artifacts/{name}')
    def artifact(flow: str, tid: str, name: str) -> FileResponse:
        if flow not in _store.FLOWS:
            raise HTTPException(400, f'unknown flow {flow}')
        if not _NAME_RE.match(name):
            raise HTTPException(400, 'invalid artifact filename')
        path = Path(_safe_path(str(cfg.storage.base_dir), flow, tid, name))
        if not path.is_file():
            raise HTTPException(404, 'artifact not found')
        return FileResponse(path)

    return router
