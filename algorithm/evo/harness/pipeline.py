from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evo.agents.action_verifier import verify_actions
from evo.agents.indexer import run_indexer
from evo.agents.synthesizer import run_synthesizer
from evo.conductor.conductor import Conductor
from evo.domain.node import NodeResolver, get_node
from evo.harness import analysis as analysis_steps
from evo.harness import data_loader, report as report_mod
from evo.harness.plan import Plan, Step, StepContext, StepOutcome
from evo.runtime.config import EvoConfig, load_config
from evo.runtime.session import (
    AnalysisSession, EmbedProvider, LLMProvider, create_session, session_scope,
)


@dataclass
class PipelineOptions:
    badcase_limit: int = 100
    score_field: str = "answer_correctness"


@dataclass
class PipelineResult:
    success: bool
    session: AnalysisSession
    report_path: Path | None = None
    markdown_path: Path | None = None
    outcomes: list[StepOutcome] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def build_standard_plan(opts: PipelineOptions, *, logger: logging.Logger | None = None) -> Plan:
    """Declaratively describe the standard full-analysis flow."""

    def _load(ctx: StepContext) -> Any:
        return data_loader.load_corpus(ctx.session)

    def _features(ctx: StepContext) -> Any:
        return analysis_steps.compute_step_features(ctx.session)

    def _cluster_global(ctx: StepContext) -> Any:
        return analysis_steps.cluster_global(
            ctx.session, badcase_limit=opts.badcase_limit, score_field=opts.score_field,
        )

    def _cluster_per_step(ctx: StepContext) -> Any:
        return analysis_steps.cluster_per_step(
            ctx.session, badcase_limit=opts.badcase_limit, score_field=opts.score_field,
        )

    def _flow(ctx: StepContext) -> Any:
        return analysis_steps.analyze_flow(ctx.session)

    def _indexer(ctx: StepContext) -> Any:
        return run_indexer(ctx.session)

    def _conduct(ctx: StepContext) -> Any:
        if ctx.session.world_store is None:
            return None
        return Conductor(ctx.session).run()

    def _synthesize(ctx: StepContext) -> Any:
        if ctx.session.world_store is None:
            return None
        result = run_synthesizer(ctx.session)
        result.actions = verify_actions(ctx.session, result.actions)
        return result

    def _build_report(ctx: StepContext) -> Any:
        return report_mod.build_report(ctx.session, ctx.get("synthesize"))

    def _persist(ctx: StepContext) -> Any:
        report = ctx.get("build_report")
        if report is None:
            return {"report": None, "markdown": None}
        return report_mod.persist_report(ctx.session, report)

    return Plan(
        steps=[
            Step("load", _load, description="Load corpus (judge+trace)"),
            Step("features", _features, description="Compute per-case step features"),
            Step("cluster_global", _cluster_global, description="Global badcase clustering"),
            Step("cluster_per_step", _cluster_per_step, optional=True,
                 description="Per-step clustering"),
            Step("flow", _flow, optional=True, description="Cross-step flow analysis",
                 skip_if=lambda ctx: not ctx.session.has_stage("cluster_per_step")),
            Step("indexer", _indexer, optional=True,
                 description="LLM-driven hypothesis seeds"),
            Step("conduct", _conduct,
                 description="Conductor batch-plans Researcher + Critic"),
            Step("synthesize", _synthesize, description="WorldModel -> ChairOutput",
                 always_run=True),
            Step("build_report", _build_report, description="Assemble report",
                 always_run=True),
            Step("persist", _persist, description="Persist artefacts",
                 always_run=True),
        ],
        logger=logger,
    )


class RAGAnalysisPipeline:
    """Thin facade running the standard plan within a session scope."""

    def __init__(
        self,
        config: EvoConfig | None = None,
        *,
        logger: logging.Logger | None = None,
        llm_provider: LLMProvider | None = None,
        embed_provider: EmbedProvider | None = None,
        node_resolver: NodeResolver = get_node,
    ) -> None:
        self.config = config or load_config()
        self.log = logger or logging.getLogger("evo.pipeline")
        self.llm_provider = llm_provider
        self.embed_provider = embed_provider
        self.node_resolver = node_resolver

    def run(self,
            badcase_limit: int = 200,
            run_id: str | None = None,
            score_field: str = "answer_correctness",
            **_kw: Any) -> PipelineResult:
        opts = PipelineOptions(badcase_limit=badcase_limit, score_field=score_field)
        session = create_session(
            config=self.config, run_id=run_id,
            llm_provider=self.llm_provider,
            embed_provider=self.embed_provider,
            node_resolver=self.node_resolver,
        )

        plan = build_standard_plan(opts, logger=self.log)
        with session_scope(session):
            result = plan.run(session)

        paths = result.get("persist") or {}
        errors = [o.error or "" for o in result.failed]
        return PipelineResult(
            success=result.success,
            session=session,
            report_path=paths.get("report"),
            markdown_path=paths.get("markdown"),
            outcomes=result.outcomes,
            elapsed_seconds=result.elapsed_seconds,
            errors=errors,
        )
