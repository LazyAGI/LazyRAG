"""Tool envelopes and report schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class ErrorCode(Enum):
    DATA_NOT_LOADED = "DATA_NOT_LOADED"
    CASE_NOT_FOUND = "CASE_NOT_FOUND"
    TRACE_NOT_FOUND = "TRACE_NOT_FOUND"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    IO_ERROR = "IO_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Severity(Enum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    CRITICAL = 3


# ---------------------------------------------------------------------------
# Tool envelopes
# ---------------------------------------------------------------------------

@dataclass
class ToolError:
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


@dataclass
class ToolMeta:
    latency_ms: Optional[float] = None
    cache_hit: Optional[bool] = None
    truncated: Optional[bool] = None


@dataclass
class ToolSuccess(Generic[T]):
    ok: bool = True
    data: Optional[T] = None
    meta: Optional[ToolMeta] = None

    def to_json(self) -> str:
        result: dict[str, Any] = {"ok": True, "data": self.data}
        if self.meta:
            result["meta"] = asdict(self.meta)
        return json.dumps(result, ensure_ascii=False, indent=2)


@dataclass
class ToolFailure:
    ok: bool = False
    error: ToolError = field(default_factory=lambda: ToolError(code=ErrorCode.INTERNAL_ERROR.value, message="Unknown error"))

    def to_json(self) -> str:
        result: dict[str, Any] = {"ok": False, "error": {"code": self.error.code, "message": self.error.message}}
        if self.error.details:
            result["error"]["details"] = self.error.details
        return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Perspective agent schemas
# ---------------------------------------------------------------------------

@dataclass
class PerspectiveHypothesis:
    stage: str
    hypothesis: str
    confidence: float
    evidence_refs: list[str]
    counterfactual_checks: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InteractionEffect:
    stages: list[str]
    description: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerspectiveReport:
    perspective: str
    dataset_ids: list[str]
    hypotheses: list[PerspectiveHypothesis]
    interaction_effects: list[InteractionEffect] = field(default_factory=list)
    per_step_diagnosis: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "perspective": self.perspective,
            "dataset_ids": self.dataset_ids,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "interaction_effects": [e.to_dict() for e in self.interaction_effects],
            "per_step_diagnosis": self.per_step_diagnosis,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Report schemas (used by tools/report.py)
# ---------------------------------------------------------------------------

@dataclass
class KeyFinding:
    severity: Severity
    field: str
    behavior: str
    range: str
    count: int
    action: str


@dataclass
class ActionItem:
    priority: int
    symptoms: str
    trigger_metric: str
    trigger_cases: list[str]
    hypothesis: str
    evidence_basis_type: str
    evidence_finding: str
    evidence_confidence: float
    changes: dict[str, Any]
    validation_cases: list[str]
    owner_team_suggestion: Optional[str] = None
    verification_metric: Optional[str] = None
    rollback_metric: Optional[str] = None


@dataclass
class AbTestPolicy:
    success_criteria: dict[str, Any]
    early_stop: dict[str, Any]
    control_group_size: int = 1000
    experiment_group_size: int = 1000


@dataclass
class DiagnosisReport:
    report_id: str
    metadata: dict[str, Any]
    summary: dict[str, Any]
    key_findings: dict[str, KeyFinding]
    expected_edit: dict[str, Any]
    action_list: dict[str, ActionItem]
    abtest_strategy: AbTestPolicy
    guidance: str = ""
    per_step_diagnosis: list[dict[str, Any]] = field(default_factory=list)
    global_step_analysis: dict[str, Any] = field(default_factory=dict)
    chair_summary: str = ""
    chair_parse_failed: bool = False
    interaction_effects: Optional[Any] = None
    cross_case_patterns: Optional[Any] = None
    causal_chains: Optional[Any] = None
    code_correlations: Optional[Any] = None
    modification_plan: Optional[Any] = None


@dataclass
class CaseEvidence:
    dataset_id: str
    pipeline: list[str]
    judge_metrics: dict[str, float]
    judge_texts: dict[str, Any]
    step_summaries: dict[str, dict[str, Any]]
    step_features: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
