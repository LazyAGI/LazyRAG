from __future__ import annotations

from fastapi import APIRouter

from evo.service.api.lifecycle import lifecycle_router
from evo.service.core.manager import JobManager
from evo.service.core.schemas import DeployCreate


def build_deploys_router(jm: JobManager) -> APIRouter:
    return lifecycle_router(
        jm,
        flow='deploy',
        prefix='/v1/evo/deploys',
        create_model=DeployCreate,
        start_op='deploy.start',
        action_ops={'cancel': 'deploy.cancel', 'continue': 'deploy.continue'},
    )
