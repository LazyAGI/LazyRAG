from __future__ import annotations

from fastapi import APIRouter, Query

from evo.service.core.manager import JobManager
from evo.service.core.schemas import RunCreate
from evo.service.api.lifecycle import lifecycle_router


def build_runs_router(jm: JobManager) -> APIRouter:
    router = lifecycle_router(
        jm,
        flow='run',
        prefix='/v1/evo/runs',
        create_model=RunCreate,
        start_op='run.start',
        action_ops={'stop': 'run.stop', 'continue': 'run.continue',
                    'cancel': 'run.cancel'},
    )

    @router.get('/{run_id}/handles')
    def handles(run_id: str, since: int = Query(0, ge=0)) -> dict:
        import json
        path = jm.config.storage.runs_dir / run_id / 'handles.jsonl'
        if not path.is_file():
            return {'handles': [], 'next': since}
        out: list[dict] = []
        next_line = since
        with path.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < since:
                    continue
                next_line = i + 1
                if not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return {'handles': out, 'next': next_line}

    return router
