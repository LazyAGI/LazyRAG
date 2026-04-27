from __future__ import annotations

from fastapi import APIRouter
from evo.service.core.manager import JobManager
from evo.service.core.schemas import DatasetGenCreate
from evo.service.api.lifecycle import lifecycle_router


def build_datasets_router(jm: JobManager) -> APIRouter:
    return lifecycle_router(
        jm,
        flow='dataset_gen',
        prefix='/v1/evo/datasets',
        create_model=DatasetGenCreate,
        start_op='dataset_gen.start',
        action_ops={'cancel': 'dataset_gen.cancel'},
    )
