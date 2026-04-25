from __future__ import annotations

from fastapi import APIRouter
from evo.service.core.manager import JobManager
from evo.service.core.schemas import EvalCreate
from evo.service.api.lifecycle import lifecycle_router


def build_evals_router(jm: JobManager) -> APIRouter:
    return lifecycle_router(
        jm,
        flow='eval',
        prefix='/v1/evo/evals',
        create_model=EvalCreate,
        start_op='eval.run',
        action_ops={'cancel': 'eval.cancel'},
        start_op_selector=lambda body: 'eval.run' if body.get('dataset_id') else 'eval.fetch',
    )
