from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from evo.agents.action_verifier import verify_actions
from evo.agents.indexer import run_indexer
from evo.agents.synthesizer import run_synthesizer
from evo.conductor.conductor import Conductor
from evo.harness import analysis as analysis_steps
from evo.harness import data_loader, report as report_mod
from evo.harness.plan import Plan, Step, StepContext
from evo.runtime.session import AnalysisSession
def _load_revise_feedback(session: AnalysisSession) -> str | None:
    path = session.config.storage.runs_dir / session.run_id / 'revise_feedback.json'
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8')).get('feedback') or None
    except (json.JSONDecodeError, KeyError):
        return None
@dataclass
class PipelineOptions:
    badcase_limit: int = 100
    score_field: str = 'answer_correctness'
def build_standard_plan(opts: PipelineOptions, *, logger: logging.Logger | None=None, judge_path: Path | None=None, trace_path: Path | None=None, before_step: Callable[[str, StepContext], None] | None=None) -> Plan:
    def _load(ctx: StepContext) -> Any:
        return data_loader.load_corpus(ctx.session, judge_path=judge_path, trace_path=trace_path)
    def _features(ctx: StepContext) -> Any:
        return analysis_steps.compute_step_features(ctx.session)
    def _cluster_global(ctx: StepContext) -> Any:
        return analysis_steps.cluster_global(ctx.session, badcase_limit=opts.badcase_limit, score_field=opts.score_field)
    def _cluster_per_step(ctx: StepContext) -> Any:
        return analysis_steps.cluster_per_step(ctx.session, badcase_limit=opts.badcase_limit, score_field=opts.score_field)
    def _flow(ctx: StepContext) -> Any:
        return analysis_steps.analyze_flow(ctx.session)
    def _indexer(ctx: StepContext) -> Any:
        feedback = _load_revise_feedback(ctx.session)
        return run_indexer(ctx.session, user_feedback=feedback)
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
        return report_mod.build_report(ctx.session, ctx.get('synthesize'))
    def _persist(ctx: StepContext) -> Any:
        report = ctx.get('build_report')
        if report is None:
            return {'report': None, 'markdown': None}
        return report_mod.persist_report(ctx.session, report)
    return Plan(steps=[Step('load', _load, description='Load corpus (judge+trace)'), Step('features', _features, description='Compute per-case step features'), Step('cluster_global', _cluster_global, description='Global badcase clustering'), Step('cluster_per_step', _cluster_per_step, optional=True, description='Per-step clustering'), Step('flow', _flow, optional=True, description='Cross-step flow analysis', skip_if=lambda ctx: not ctx.session.has_stage('cluster_per_step')), Step('indexer', _indexer, optional=True, description='LLM-driven hypothesis seeds'), Step('conduct', _conduct, description='Conductor batch-plans Researcher + Critic'), Step('synthesize', _synthesize, description='WorldModel -> ChairOutput', always_run=True), Step('build_report', _build_report, description='Assemble report', always_run=True), Step('persist', _persist, description='Persist artefacts', always_run=True)], logger=logger, before_step=before_step)
