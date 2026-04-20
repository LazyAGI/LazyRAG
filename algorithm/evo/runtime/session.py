from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from evo.domain import (
    ClusteringResult, FlowAnalysisResult, JudgeRecord,
    MergedCaseView, NodeInfo, NodeResolver, PerStepClusteringResult,
    TraceMeta, TraceRecord, get_node,
)
from evo.conductor.handle_store import HandleStore
from evo.conductor.world_model import WorldModelStore
from evo.runtime.config import EvoConfig
from evo.runtime.model_gateway import ModelGateway
from evo.runtime.state import SessionState
from evo.runtime.telemetry import Handler, TelemetrySink

LLMProvider = Callable[[], Any]
EmbedProvider = Callable[[], Any]  # factory returns an embed model callable: text -> vector

_current: ContextVar['AnalysisSession | None'] = ContextVar('evo_session', default=None)


def get_current_session() -> 'AnalysisSession | None':
    return _current.get()


def require_session(consumer: str = 'tool') -> 'AnalysisSession':
    s = _current.get()
    if s is None:
        raise RuntimeError(f'No active session for {consumer}; wrap with session_scope().')
    return s


class session_scope:
    def __init__(self, session: 'AnalysisSession') -> None:
        self._session = session
        self._token: Any = None

    def __enter__(self) -> 'AnalysisSession':
        self._token = _current.set(self._session)
        return self._session

    def __exit__(self, *exc: Any) -> None:
        _current.reset(self._token)


@dataclass
class AnalysisSession:
    run_id: str
    created_at: datetime
    config: EvoConfig
    state: SessionState = field(default_factory=SessionState)
    llm: ModelGateway = field(default=None)  # type: ignore[assignment]
    embed: ModelGateway = field(default=None)  # type: ignore[assignment]
    telemetry: TelemetrySink = field(default_factory=TelemetrySink)
    handle_store: HandleStore | None = None
    world_store: WorldModelStore | None = None
    llm_provider: LLMProvider | None = None
    embed_provider: EmbedProvider | None = None
    node_resolver: NodeResolver = field(default=get_node)
    _node_cache: dict[str, NodeInfo | None] = field(default_factory=dict, repr=False)

    # ---- lifecycle ------------------------------------------------------

    def logger(self, suffix: str = '') -> logging.Logger:
        name = f'evo.session.{self.run_id}'
        return logging.getLogger(f'{name}.{suffix}' if suffix else name)

    def mark_stage(self, stage: str) -> None:
        self.state.stages_completed.add(stage)
        self.telemetry.emit('stage.completed', stage=stage)

    def has_stage(self, stage: str) -> bool:
        return stage in self.state.stages_completed

    def on(self, event_type: str, handler: Handler) -> None:
        self.telemetry.on(event_type, handler)

    # ---- corpus accessors ----------------------------------------------

    @property
    def parsed_judge(self) -> dict[str, JudgeRecord]:
        return self.state.parsed_judge

    @property
    def parsed_trace(self) -> dict[str, TraceRecord]:
        return self.state.parsed_trace

    @property
    def trace_meta(self) -> TraceMeta:
        return self.state.trace_meta

    @property
    def eval_report_meta(self) -> dict[str, Any] | None:
        return self.state.eval_report_meta

    @property
    def warnings(self) -> list[str]:
        return list(self.state.warnings)

    # ---- derived state accessors ---------------------------------------

    @property
    def case_step_features(self) -> dict[str, dict[str, dict[str, float]]]:
        return self.state.case_step_features

    @property
    def global_step_analysis(self) -> dict[str, Any]:
        return self.state.global_step_analysis

    @property
    def clustering_global(self) -> ClusteringResult | None:
        return self.state.clustering_global

    @property
    def clustering_per_step(self) -> PerStepClusteringResult | None:
        return self.state.clustering_per_step

    @property
    def flow_analysis(self) -> FlowAnalysisResult | None:
        return self.state.flow_analysis

    @property
    def artifacts(self) -> dict[str, Path]:
        return self.state.artifacts

    @property
    def stages_completed(self) -> frozenset[str]:
        return frozenset(self.state.stages_completed)

    # ---- judge / trace lookup ------------------------------------------

    def list_dataset_ids(self) -> list[str]:
        return list(self.state.parsed_judge.keys())

    def iter_judge(self) -> Iterator[tuple[str, JudgeRecord]]:
        yield from self.state.parsed_judge.items()

    def get_judge(self, dataset_id: str) -> JudgeRecord | None:
        return self.state.parsed_judge.get(dataset_id)

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        return self.state.parsed_trace.get(trace_id)

    def get_merged_case(self, dataset_id: str) -> MergedCaseView:
        j = self.state.parsed_judge.get(dataset_id)
        if j is None:
            raise KeyError(f'Dataset ID not found: {dataset_id}')
        t = self.state.parsed_trace.get(j.trace_id)
        if t is None:
            raise ValueError(f'Trace {j.trace_id} not found for {dataset_id}')
        return MergedCaseView(dataset_id=dataset_id, query=t.query, judge=j, trace=t)

    # ---- node resolution (injected via ``node_resolver``) --------------

    def resolve_node(self, node_id: str) -> NodeInfo | None:
        if not node_id:
            return None
        cache = self._node_cache
        if node_id in cache:
            return cache[node_id]
        try:
            info = self.node_resolver(node_id)
        except Exception as exc:
            self.logger('node_resolver').debug(
                'get_node(%r) failed: %s', node_id, exc,
            )
            info = None
        cache[node_id] = info
        return info

    def score_lookup(self, score_field: str) -> Callable[[str], float | None]:
        def _lookup(dataset_id: str) -> float | None:
            j = self.state.parsed_judge.get(dataset_id)
            if j is None:
                return None
            v = getattr(j, score_field, None)
            return float(v) if isinstance(v, (int, float)) else None
        return _lookup

    # ---- controlled setters --------------------------------------------

    def set_parsed_corpus(
        self,
        judges: dict[str, JudgeRecord],
        traces: dict[str, TraceRecord],
        trace_meta: TraceMeta,
        *,
        warnings: list[str] | None = None,
        eval_report_meta: dict[str, Any] | None = None,
    ) -> None:
        self.state.parsed_judge = dict(judges)
        self.state.parsed_trace = dict(traces)
        self.state.trace_meta = trace_meta
        if warnings:
            self.state.warnings.extend(warnings)
        if eval_report_meta is not None:
            self.state.eval_report_meta = dict(eval_report_meta)
        self.telemetry.emit('corpus.loaded',
                            judges=len(judges), traces=len(traces),
                            pipeline=list(trace_meta.pipeline))

    def set_step_features(
        self,
        case_features: dict[str, dict[str, dict[str, float]]],
        global_features: dict[str, Any],
    ) -> None:
        self.state.case_step_features = dict(case_features)
        self.state.global_step_analysis = dict(global_features)
        self.telemetry.emit('features.ready', cases=len(case_features))

    def set_clustering_global(self, result: ClusteringResult) -> None:
        self.state.clustering_global = result
        self.telemetry.emit('clustering.global.ready',
                            n_clusters=result.n_clusters, n_cases=result.n_cases)

    def set_clustering_per_step(self, result: PerStepClusteringResult) -> None:
        self.state.clustering_per_step = result
        self.telemetry.emit('clustering.per_step.ready',
                            steps=list(result.per_step.keys()))

    def set_flow_analysis(self, result: FlowAnalysisResult) -> None:
        self.state.flow_analysis = result
        self.telemetry.emit('flow.ready',
                            critical_steps=list(result.critical_steps))

    def add_artifact(self, key: str, path: Path) -> None:
        self.state.artifacts[key] = path
        self.telemetry.emit('artifact.added', key=key, path=str(path))


def create_session(
    config: EvoConfig | None = None,
    *,
    run_id: str | None = None,
    llm_provider: LLMProvider | None = None,
    embed_provider: EmbedProvider | None = None,
    node_resolver: NodeResolver = get_node,
) -> AnalysisSession:
    if config is None:
        from evo.runtime.config import load_config
        config = load_config()
    if run_id is None:
        run_id = f'run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'

    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / 'reports').mkdir(parents=True, exist_ok=True)
    telemetry_path = config.output_dir / 'telemetry' / f'{run_id}.jsonl'
    run_dir = config.output_dir / 'runs' / run_id
    handle_store = HandleStore(run_dir / 'handles.jsonl')
    world_store = WorldModelStore(run_dir / 'world_model.json', run_id=run_id)

    session = AnalysisSession(
        run_id=run_id,
        created_at=datetime.now(),
        config=config,
        telemetry=TelemetrySink(path=telemetry_path),
        handle_store=handle_store,
        world_store=world_store,
        llm_provider=llm_provider,
        embed_provider=embed_provider,
        node_resolver=node_resolver,
    )
    on_event = session.telemetry.as_callback()
    session.llm = ModelGateway(config.llm, name='llm',
                               logger=session.logger('llm'), on_event=on_event)
    session.embed = ModelGateway(config.embed, name='embed',
                                 logger=session.logger('embed'), on_event=on_event)
    return session
