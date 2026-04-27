from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from evo.apply.errors import ApplyError
from evo.service.core.errors import StateError


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(StateError)
    async def _state_err(_req: Request, exc: StateError) -> JSONResponse:
        status = {
            'ILLEGAL_TRANSITION': 409,
            'ACTIVE_TASK_EXISTS': 409,
            'TASK_NOT_FOUND': 404,
            'INVALID_FLOW': 400,
            'NO_REPORT_AVAILABLE': 409,
        }.get(exc.code, 400)
        return JSONResponse(status_code=status, content={
            'code': exc.code, 'kind': 'permanent',
            'message': exc.message, 'details': exc.details,
        })

    @app.exception_handler(ApplyError)
    async def _apply_err(_req: Request, exc: ApplyError) -> JSONResponse:
        status = 409 if exc.kind == 'permanent' else 503
        return JSONResponse(status_code=status, content=exc.to_payload())
