from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body, Header, Query, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from evo.service.core import store as _store
from evo.service.core.manager import JobManager
from evo.service.core.ops_executor import Op, OpResult, OpsExecutor


def lifecycle_router(
    jm: JobManager,
    *,
    flow: str,
    prefix: str,
    create_model: type[BaseModel],
    start_op: str,
    action_ops: dict[str, str] | None = None,
    get_task_hook: Callable[[str, dict], dict] | None = None,
    start_op_selector: Callable[[dict], str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[flow])
    ops = OpsExecutor(jm)
    action_ops = action_ops or {}
    resolve_start_op = start_op_selector or (lambda _body: start_op)

    @router.post('', response_model=dict)
    async def create(
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
        idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    ) -> dict:
        payload = create_model(**body).model_dump(exclude_none=True)
        op = resolve_start_op(payload)

        def run() -> dict:
            result = ops.execute([Op(op, payload)])[0]
            return _result_to_dict(result)

        return request.app.state.idem.get_or_run(idempotency_key, run)

    @router.get('', response_model=list[dict])
    def list_recent(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return jm.list_recent(flow, limit)

    @router.get('/{task_id}', response_model=dict)
    def get_task(task_id: str) -> dict:
        row = _store.must_get(jm.conn, task_id)
        if get_task_hook is not None:
            row = get_task_hook(task_id, row)
        return row

    @router.post('/{task_id}/cancel', response_model=dict)
    async def cancel(task_id: str) -> dict:
        result = ops.execute([Op(action_ops.get('cancel', f'{flow}.cancel'),
                                 {'task_id': task_id})])[0]
        return _result_to_dict(result)

    if 'stop' in action_ops:
        @router.post('/{task_id}/stop', response_model=dict)
        async def stop(task_id: str) -> dict:
            result = ops.execute([Op(action_ops['stop'], {'task_id': task_id})])[0]
            return _result_to_dict(result)

    if 'continue' in action_ops:
        @router.post('/{task_id}/continue', response_model=dict)
        async def cont(task_id: str) -> dict:
            result = ops.execute([Op(action_ops['continue'], {'task_id': task_id})])[0]
            return _result_to_dict(result)

    @router.get('/{task_id}/events')
    async def events(task_id: str) -> EventSourceResponse:
        from evo.service import sse
        path = _events_path(jm, flow, task_id)
        return EventSourceResponse(sse.tail_jsonl(jm.conn, task_id, path))

    return router


def _result_to_dict(result: OpResult) -> dict:
    return {
        'op': result.op,
        'task_id': result.task_id,
        'status': result.status,
        'error': result.error,
        'data': result.data,
    }


def _events_path(jm: JobManager, flow: str, task_id: str):
    if flow == 'run':
        return jm.config.storage.runs_dir / task_id / 'telemetry.jsonl'
    if flow == 'apply':
        return jm.config.storage.applies_dir / task_id / 'telemetry.jsonl'
    if flow == 'eval':
        return jm.config.storage.base_dir / 'evals' / task_id / 'telemetry.jsonl'
    return jm.config.storage.base_dir / flow / task_id / 'telemetry.jsonl'
