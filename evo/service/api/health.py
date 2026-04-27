from __future__ import annotations

from fastapi import APIRouter


def build_health_router() -> APIRouter:
    router = APIRouter(prefix='', tags=['health'])

    @router.get('/healthz')
    def healthz() -> dict:
        return {'ok': True}

    @router.get('/livez')
    def livez() -> dict:
        return {'alive': True}

    @router.get('/readyz')
    def readyz() -> dict:
        return {'ready': True}

    return router
