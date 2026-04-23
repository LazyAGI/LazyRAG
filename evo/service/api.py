from __future__ import annotations

import json
import time
from typing import Any

from fastapi import (Body, Depends, FastAPI, Header, HTTPException, Query,
                      Request, Response)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from evo.apply.errors import ApplyError
from evo.runtime.config import EvoConfig, load_config
from evo.service import jobs, opencode_admin, sse, state

_IDEMPOTENCY_TTL = 30.0

API_DESCRIPTION = """
Evo POC service.

Two flows: **run** (diagnosis) and **apply** (code modification driven by opencode).
Each flow is a single-admin singleton: only one non-terminal task per flow at a time.

State machine (per flow):
queued -> running -> stopping -> paused -> running -> succeeded
                  -> failed_transient -> running
                  -> failed_permanent -> cancelled
apply: succeeded -> accepted | rejected
"""


# ---------- request / response schemas ----------

class TaskId(BaseModel):
    id: str


class ApplyCreate(BaseModel):
    report_id: str | None = None


class OpencodeCfg(BaseModel):
    provider: str
    api_key: str
    model: str | None = None


class OpencodeStatus(BaseModel):
    authenticated: bool
    path: str
    providers: list[str]
    last_check_at: float


class ReportRef(BaseModel):
    report_id: str
    json_path: str
    markdown_path: str | None


class HandlesPage(BaseModel):
    handles: list[dict]
    next: int


# ---------- internal helpers ----------

class _Idempotency:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}

    def _evict(self) -> None:
        now = time.time()
        stale = [k for k, (ts, _) in self._cache.items() if now - ts > _IDEMPOTENCY_TTL]
        for k in stale:
            self._cache.pop(k, None)

    def get_or_run(self, key: str | None, run_fn) -> Any:
        if not key:
            return run_fn()
        self._evict()
        hit = self._cache.get(key)
        if hit is not None:
            return hit[1]
        value = run_fn()
        self._cache[key] = (time.time(), value)
        return value


def _idem_key(idempotency_key: str | None = Header(default=None,
                                                    alias='Idempotency-Key')):
    return idempotency_key


# ---------- app factory ----------

def create_app(config: EvoConfig | None = None,
               *, job_manager: jobs.JobManager | None = None) -> FastAPI:
    cfg = config or load_config()
    jm = job_manager if job_manager is not None else jobs.get_manager(cfg)
    app = FastAPI(title='evo service', version='poc-1',
                  description=API_DESCRIPTION,
                  openapi_tags=[
                      {'name': 'runs', 'description': 'Diagnosis flow'},
                      {'name': 'applies', 'description': 'Code modification flow'},
                      {'name': 'reports', 'description': 'Final reports & diffs'},
                      {'name': 'admin', 'description': 'opencode credential management'},
                      {'name': 'health', 'description': 'Liveness probe'},
                  ])
    app.state.cfg = cfg
    app.state.jm = jm
    app.state.idem = _Idempotency()

    _register_exception_handlers(app)
    _register_run_routes(app, cfg, jm)
    _register_apply_routes(app, cfg, jm)
    _register_artifact_routes(app, cfg)
    _register_admin_routes(app, cfg)

    @app.get('/healthz', tags=['health'], summary='Liveness probe')
    def healthz() -> dict:
        return {'ok': True}

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(state.StateError)
    async def _state_err(_req: Request, exc: state.StateError) -> JSONResponse:
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


# ---------- run routes ----------

def _register_run_routes(app: FastAPI, cfg: EvoConfig, jm: jobs.JobManager) -> None:
    tag = ['runs']

    @app.post('/v1/evo/runs', tags=tag, response_model=TaskId,
              summary='Start a diagnosis run')
    async def create_run(idem: str | None = Depends(_idem_key)) -> dict:
        return app.state.idem.get_or_run(idem, lambda: {'id': jm.submit_run()})

    @app.get('/v1/evo/runs', tags=tag, summary='List recent runs')
    def list_runs(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return jm.list_recent('run', limit)

    @app.get('/v1/evo/runs/{run_id}', tags=tag, summary='Get run state')
    def get_run(run_id: str) -> dict:
        return state.must_get(jm.conn, run_id)

    @app.post('/v1/evo/runs/{run_id}/stop', tags=tag, summary='Request stop (graceful, keeps logs)')
    async def stop_run(run_id: str) -> dict:
        return jm.stop(run_id)

    @app.post('/v1/evo/runs/{run_id}/continue', tags=tag, summary='Resume from last checkpoint')
    async def continue_run(run_id: str) -> dict:
        return jm.cont(run_id)

    @app.post('/v1/evo/runs/{run_id}/cancel', tags=tag, summary='Cancel; deletes run dir')
    async def cancel_run(run_id: str) -> dict:
        return jm.cancel(run_id)

    @app.get('/v1/evo/runs/{run_id}/telemetry', tags=tag,
             summary='SSE stream of telemetry events')
    async def stream_run_telemetry(run_id: str) -> EventSourceResponse:
        path = cfg.storage.runs_dir / run_id / 'telemetry.jsonl'
        return EventSourceResponse(sse.tail_jsonl(jm.conn, run_id, path))

    @app.get('/v1/evo/runs/{run_id}/world', tags=tag, summary='WorldModel snapshot')
    def world(run_id: str) -> dict:
        path = cfg.storage.runs_dir / run_id / 'world_model.json'
        if not path.is_file():
            raise HTTPException(404, 'world_model not yet written')
        return json.loads(path.read_text(encoding='utf-8'))

    @app.get('/v1/evo/runs/{run_id}/handles', tags=tag,
             response_model=HandlesPage, summary='Tool-call handle log (paged)')
    def handles(run_id: str, since: int = Query(0, ge=0)) -> dict:
        path = cfg.storage.runs_dir / run_id / 'handles.jsonl'
        if not path.is_file():
            return {'handles': [], 'next': since}
        out: list[dict] = []
        with path.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < since or not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return {'handles': out, 'next': since + len(out)}

    @app.get('/v1/evo/runs/{run_id}/report', tags=tag,
             response_model=ReportRef, summary='Latest report metadata for this run')
    def latest_report_for_run(run_id: str) -> dict:
        for p in sorted(cfg.storage.reports_dir.glob('*.json'),
                        key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
            if data.get('metadata', {}).get('run_id') == run_id:
                rid = data.get('report_id') or p.stem
                md = p.with_suffix('.md')
                return {'report_id': rid, 'json_path': str(p),
                        'markdown_path': str(md) if md.is_file() else None}
        raise HTTPException(404, 'no report for this run')


# ---------- apply routes ----------

def _register_apply_routes(app: FastAPI, cfg: EvoConfig, jm: jobs.JobManager) -> None:
    tag = ['applies']

    @app.post('/v1/evo/applies', tags=tag, response_model=TaskId,
              summary='Start an apply (defaults to latest succeeded run report)')
    async def create_apply(body: ApplyCreate = Body(default_factory=ApplyCreate),
                            idem: str | None = Depends(_idem_key)) -> dict:
        return app.state.idem.get_or_run(
            idem, lambda: {'id': jm.submit_apply(report_id=body.report_id)})

    @app.get('/v1/evo/applies', tags=tag, summary='List recent applies')
    def list_applies(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return jm.list_recent('apply', limit)

    @app.get('/v1/evo/applies/{apply_id}', tags=tag,
             summary='Get apply state with rounds')
    def get_apply(apply_id: str) -> dict:
        row = state.must_get(jm.conn, apply_id)
        row['rounds'] = jm.list_rounds(apply_id)
        return row

    @app.post('/v1/evo/applies/{apply_id}/stop', tags=tag, summary='Request stop')
    async def stop_apply(apply_id: str) -> dict:
        return jm.stop(apply_id)

    @app.post('/v1/evo/applies/{apply_id}/continue', tags=tag, summary='Resume from last round')
    async def continue_apply(apply_id: str) -> dict:
        return jm.cont(apply_id)

    @app.post('/v1/evo/applies/{apply_id}/cancel', tags=tag,
              summary='Cancel; SIGTERM opencode + delete worktree, branch, diffs, logs')
    async def cancel_apply(apply_id: str) -> dict:
        return jm.cancel(apply_id)

    @app.post('/v1/evo/applies/{apply_id}/accept', tags=tag,
              summary='Accept the diff; keeps everything, marks DB accepted')
    async def accept_apply(apply_id: str) -> dict:
        return jm.accept(apply_id)

    @app.post('/v1/evo/applies/{apply_id}/reject', tags=tag,
              summary='Reject; drops worktree+branch+diffs but keeps round logs')
    async def reject_apply(apply_id: str) -> dict:
        return jm.reject(apply_id)

    @app.get('/v1/evo/applies/{apply_id}/telemetry', tags=tag,
             summary='SSE stream of round events')
    async def stream_apply_telemetry(apply_id: str) -> EventSourceResponse:
        path = cfg.storage.applies_dir / apply_id / 'telemetry.jsonl'
        return EventSourceResponse(sse.tail_jsonl(jm.conn, apply_id, path))

    @app.get('/v1/evo/applies/{apply_id}/diff-map', tags=tag,
             summary='Self-describing diff index (per-file change kinds + diff URIs)')
    def diff_map(apply_id: str) -> dict:
        path = cfg.storage.diffs_dir / apply_id / 'index.json'
        if not path.is_file():
            raise HTTPException(404, 'diff-map not generated')
        return json.loads(path.read_text(encoding='utf-8'))


# ---------- artifact routes ----------

def _register_artifact_routes(app: FastAPI, cfg: EvoConfig) -> None:
    tag = ['reports']

    @app.get('/v1/evo/reports/{report_id}/content', tags=tag,
             summary='Download a report (json or md)')
    def report_content(report_id: str,
                       fmt: str = Query('json', pattern='^(json|md)$')) -> Response:
        suffix = '.json' if fmt == 'json' else '.md'
        path = cfg.storage.reports_dir / f'{report_id}{suffix}'
        if not path.is_file():
            raise HTTPException(404, f'report {report_id}.{fmt} not found')
        return FileResponse(path, media_type='application/json' if fmt == 'json'
                            else 'text/markdown')

    @app.get('/v1/evo/diffs/{apply_id}/{filename}', tags=tag,
             summary='Download a per-file unified diff')
    def diff_file(apply_id: str, filename: str) -> FileResponse:
        if '/' in filename or '..' in filename or not filename.endswith('.diff'):
            raise HTTPException(400, 'invalid diff filename')
        path = cfg.storage.diffs_dir / apply_id / filename
        if not path.is_file():
            raise HTTPException(404, 'diff file not found')
        return FileResponse(path, media_type='text/x-diff')


# ---------- admin routes ----------

def _register_admin_routes(app: FastAPI, cfg: EvoConfig) -> None:
    tag = ['admin']

    @app.get('/v1/evo/admin/opencode/status', tags=tag,
             response_model=OpencodeStatus,
             summary='Whether opencode is authenticated')
    def admin_opencode_status() -> dict:
        return opencode_admin.read_status(cfg)

    @app.put('/v1/evo/admin/opencode/config', tags=tag,
             response_model=OpencodeStatus,
             summary='Set/replace an opencode provider credential')
    def admin_opencode_set(body: OpencodeCfg) -> dict:
        return opencode_admin.write_config(
            cfg, provider=body.provider, api_key=body.api_key, model=body.model)

    @app.delete('/v1/evo/admin/opencode/config', tags=tag,
                response_model=OpencodeStatus,
                summary='Clear all opencode credentials')
    def admin_opencode_clear() -> dict:
        return opencode_admin.clear_config(cfg)


# ---------- entrypoint factory (uvicorn --factory) ----------

def get_app() -> FastAPI:
    return create_app()
