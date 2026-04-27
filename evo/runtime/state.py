from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evo.domain import (
    ClusteringResult, FlowAnalysisResult, JudgeRecord,
    PerStepClusteringResult, TraceMeta, TraceRecord,
)


@dataclass
class SessionState:
    """All mutable state for a single analysis run."""

    # Raw corpora -----------------------------------------------------------
    parsed_judge: dict[str, JudgeRecord] = field(default_factory=dict)
    parsed_trace: dict[str, TraceRecord] = field(default_factory=dict)
    trace_meta: TraceMeta = field(default_factory=TraceMeta)
    eval_report_meta: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    # Feature engineering ---------------------------------------------------
    case_step_features: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    global_step_analysis: dict[str, Any] = field(default_factory=dict)

    # Clustering & flow -----------------------------------------------------
    clustering_global: ClusteringResult | None = None
    clustering_per_step: PerStepClusteringResult | None = None
    flow_analysis: FlowAnalysisResult | None = None

    # Artifacts -------------------------------------------------------------
    artifacts: dict[str, Path] = field(default_factory=dict)

    # Stage flags (drive declarative step skipping) -------------------------
    stages_completed: set[str] = field(default_factory=set)
