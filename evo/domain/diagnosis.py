from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiagnosisReport:
    report_id: str
    metadata: dict[str, Any]
    summary: str = ''
    guidance: str = ''
    actions: list[dict[str, Any]] = field(default_factory=list)
    open_gaps: list[str] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    global_step_analysis: dict[str, Any] = field(default_factory=dict)
    flow_analysis: dict[str, Any] | None = None
    synthesizer_iterations: int = 0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            'report_id': self.report_id,
            'metadata': self.metadata,
            'summary': self.summary,
            'guidance': self.guidance,
            'actions': self.actions,
            'open_gaps': self.open_gaps,
            'hypotheses': self.hypotheses,
            'findings': self.findings,
            'global_step_analysis': self.global_step_analysis,
            'synthesizer_iterations': self.synthesizer_iterations,
        }
        if self.flow_analysis is not None:
            out['flow_analysis'] = self.flow_analysis
        return out
