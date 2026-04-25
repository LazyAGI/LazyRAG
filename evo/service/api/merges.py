from __future__ import annotations

from fastapi import APIRouter

from evo.service.api.lifecycle import lifecycle_router
from evo.service.core.manager import JobManager
from evo.service.core.schemas import MergeCreate


def build_merges_router(jm: JobManager) -> APIRouter:
    return lifecycle_router(
        jm,
        flow='merge',
        prefix='/v1/evo/merges',
        create_model=MergeCreate,
        start_op='merge.start',
        action_ops={'cancel': 'merge.cancel'},
    )
