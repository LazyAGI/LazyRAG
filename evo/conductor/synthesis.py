from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Priority = Literal["P0", "P1", "P2"]
Direction = Literal["+", "-"]

PRIORITY_ORDER: tuple[Priority, ...] = ("P0", "P1", "P2")
DIRECTION_VALUES: tuple[Direction, ...] = ("+", "-")


@dataclass
class VerifiedAction:
    id: str
    finding_id: str
    hypothesis_id: str
    hypothesis_category: str
    title: str
    rationale: str
    suggested_changes: str
    priority: Priority
    expected_impact_metric: str
    expected_direction: Direction
    confidence: float
    evidence_handles: list[str] = field(default_factory=list)
    validity_score: float = 0.0
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    verifier_notes: list[str] = field(default_factory=list)
    code_map_target: str = ""
    code_map_in_scope: bool = True
    code_map_warning: str = ""
    target_step: str = ""
    target_line: int = 0


@dataclass
class SynthesisResult:
    summary: str = ""
    guidance: str = ""
    actions: list[VerifiedAction] = field(default_factory=list)
    open_gaps: list[str] = field(default_factory=list)
    iterations: int = 0
