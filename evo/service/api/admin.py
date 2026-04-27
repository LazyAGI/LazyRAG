from __future__ import annotations

import os

from fastapi import APIRouter, Body, HTTPException, Query, Header
from sse_starlette.sse import EventSourceResponse

from evo.service.core.manager import JobManager
from evo.service.core import store as _store


def build_admin_router(jm: JobManager) -> APIRouter:
    router = APIRouter(prefix='/v1/evo/admin', tags=['admin'])

    @router.get('/opencode/status')
    def status() -> dict:
        from evo.service import opencode_admin
        return opencode_admin.read_status(jm.config)

    @router.put('/opencode/config')
    def set_config(body: dict = Body(...)) -> dict:
        from evo.service import opencode_admin
        return opencode_admin.write_config(
            jm.config, provider=body['provider'],
            api_key=body['api_key'], model=body.get('model'))

    @router.delete('/opencode/config')
    def clear_config() -> dict:
        from evo.service import opencode_admin
        return opencode_admin.clear_config(jm.config)

    @router.post('/{flow}s:cancelAll')
    def cancel_all(flow: str, scope: str = Query('thread'),
                   thread_id: str | None = Query(None),
                   authorization: str | None = Header(None)) -> list[dict]:
        if flow not in _store.FLOWS:
            raise HTTPException(400, f'unknown flow {flow}')
        if scope == 'global':
            admin_token = os.getenv('EVO_ADMIN_TOKEN')
            if not admin_token:
                raise HTTPException(503, 'EVO_ADMIN_TOKEN not configured')
            auth = (authorization or '').replace('Bearer ', '')
            if auth != admin_token:
                raise HTTPException(401, 'invalid admin token')
            return jm.cancel_all(flow)
        if scope == 'thread':
            if not thread_id:
                raise HTTPException(400, 'thread scope requires thread_id query')
            return jm.cancel_all(flow, thread_id=thread_id)
        raise HTTPException(400, f'unknown scope {scope}')

    @router.post('/{flow}s:stopAll')
    def stop_all(flow: str, scope: str = Query('thread'),
                 thread_id: str | None = Query(None),
                 authorization: str | None = Header(None)) -> list[dict]:
        if flow not in _store.FLOWS:
            raise HTTPException(400, f'unknown flow {flow}')
        if scope == 'global':
            admin_token = os.getenv('EVO_ADMIN_TOKEN')
            if not admin_token:
                raise HTTPException(503, 'EVO_ADMIN_TOKEN not configured')
            auth = (authorization or '').replace('Bearer ', '')
            if auth != admin_token:
                raise HTTPException(401, 'invalid admin token')
            return jm.stop_all(flow)
        if scope == 'thread':
            if not thread_id:
                raise HTTPException(400, 'thread scope requires thread_id query')
            return jm.stop_all(flow, thread_id=thread_id)
        raise HTTPException(400, f'unknown scope {scope}')

    return router
