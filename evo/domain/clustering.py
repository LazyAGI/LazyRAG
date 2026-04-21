from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClusterSummary:
    cluster_id: str
    size: int
    score_stats: dict[str, float | None]
    top_feature_deltas: dict[str, float] = field(default_factory=dict)
    step_grouped_deltas: dict[str, dict[str, float]] = field(default_factory=dict)
    exemplar_case_ids: list[str] = field(default_factory=list)


@dataclass
class ClusteringResult:
    method: str
    n_cases: int
    n_clusters: int
    noise_count: int
    cluster_summaries: list[ClusterSummary] = field(default_factory=list)


@dataclass
class PerStepSummary:
    n_cases: int
    n_clusters: int = 0
    skipped: bool = False
    cluster_summaries: list[ClusterSummary] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)


@dataclass
class PerStepClusteringResult:
    pipeline: list[str]
    per_step: dict[str, PerStepSummary]


@dataclass
class StepTransition:
    from_step: str
    to_step: str
    entropy_from: float
    entropy_to: float
    entropy_change: float
    nmi: float
    type: str
    transition_matrix: list[list[int]]
    from_clusters: list[str]
    to_clusters: list[str]


@dataclass
class FlowAnalysisResult:
    transition_analysis: list[StepTransition] = field(default_factory=list)
    critical_steps: list[str] = field(default_factory=list)
    case_label_flow: dict[str, dict[str, str]] = field(default_factory=dict)
