from __future__ import annotations

from fastapi import APIRouter
from evo.service.core.manager import JobManager
from evo.service.core.schemas import EvalCreate
from evo.service.api.lifecycle import lifecycle_router


def build_evals_router(jm: JobManager) -> APIRouter:
    def _select_eval_op(body: dict) -> str:
        has_dataset = bool(body.get('dataset_id'))
        has_eval = bool(body.get('eval_id'))
        if has_dataset == has_eval:
            raise ValueError('provide exactly one of dataset_id or eval_id')
        return 'eval.run' if has_dataset else 'eval.fetch'

    return lifecycle_router(
        jm,
        flow='eval',
        prefix='/v1/evo/evals',
        create_model=EvalCreate,
        start_op='eval.run',
        action_ops={'cancel': 'eval.cancel'},
        start_op_selector=_select_eval_op,
    )
