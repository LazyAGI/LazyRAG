from __future__ import annotations

from fastapi import APIRouter
from evo.service.core.manager import JobManager
from evo.service.core.schemas import AbtestCreate
from evo.service.api.lifecycle import lifecycle_router


def build_abtests_router(jm: JobManager) -> APIRouter:
    return lifecycle_router(
        jm,
        flow='abtest',
        prefix='/v1/evo/abtests',
        create_model=AbtestCreate,
        start_op='abtest.create',
        action_ops={'stop': 'abtest.stop', 'continue': 'abtest.continue',
                    'cancel': 'abtest.cancel'},
    )
