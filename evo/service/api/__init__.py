from __future__ import annotations

from fastapi import FastAPI

from evo.runtime.config import EvoConfig
from evo.service.core.manager import JobManager
from evo.service.api import (
    runs, applies, evals, datasets, abtests, merges, deploys,
    admin, artifacts, health,
)


def create_app(config: EvoConfig | None = None,
               *, job_manager: JobManager | None = None,
               thread_hub: 'Any | None' = None) -> FastAPI:
    from evo.runtime.config import load_config
    from evo.service.api.idem import _Idempotency
    from evo.service.api.errors import register_handlers

    cfg = config or load_config()
    jm = job_manager if job_manager is not None else __import__('evo.service.core.manager', fromlist=['build_manager']).build_manager(cfg)
    app = FastAPI(title='evo service', version='poc-2')
    app.state.cfg = cfg
    app.state.jm = jm
    app.state.idem = _Idempotency()

    register_handlers(app)

    app.include_router(runs.build_runs_router(jm))
    app.include_router(applies.build_applies_router(jm))
    app.include_router(evals.build_evals_router(jm))
    app.include_router(datasets.build_datasets_router(jm))
    app.include_router(abtests.build_abtests_router(jm))
    app.include_router(merges.build_merges_router(jm))
    app.include_router(deploys.build_deploys_router(jm))
    app.include_router(admin.build_admin_router(jm))
    app.include_router(artifacts.build_artifacts_router(cfg))
    app.include_router(health.build_health_router())

    from evo.service.threads import ThreadHub, mount as mount_hub
    from evo.service.core.intent_store import IntentStore
    from evo.service.core.ops_executor import OpsExecutor
    from evo.orchestrator.planner import Planner
    from evo.orchestrator.llm import get_automodel

    planner = Planner(llm=lambda prompt: get_automodel(cfg.model_config.llm_role)(prompt))
    intent_store = IntentStore(cfg.storage.base_dir / 'state' / 'intents')
    ops = OpsExecutor(jm)
    hub = ThreadHub(jm=jm, planner=planner, intent_store=intent_store, ops=ops)
    mount_hub(app, hub)

    return app


def get_app() -> FastAPI:
    return create_app()
