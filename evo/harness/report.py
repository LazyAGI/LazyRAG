from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from evo.conductor.synthesis import SynthesisResult
from evo.domain.diagnosis import DiagnosisReport
from evo.harness.persist import write_report_bundle
from evo.runtime.session import AnalysisSession
from evo.tools.report import json_to_markdown
from evo.utils import jsonable

_log = logging.getLogger("evo.harness.report")


def build_report(session: AnalysisSession,
                 synthesis: SynthesisResult | None) -> DiagnosisReport:
    timestamp = datetime.now()
    rid = f"report_{timestamp:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
    s = synthesis or SynthesisResult(summary="no synthesis")
    world = session.world_store.world if session.world_store else None
    flow = session.flow_analysis
    return DiagnosisReport(
        report_id=rid,
        metadata={
            "created_at": timestamp.isoformat(),
            "run_id": session.run_id,
            "total_cases": len(session.case_step_features) or len(session.parsed_judge),
            "pipeline": list(session.trace_meta.pipeline),
            "eval_report_meta": session.eval_report_meta,
        },
        summary=s.summary,
        guidance=s.guidance,
        actions=[asdict(a) for a in s.actions],
        open_gaps=list(s.open_gaps),
        hypotheses=[asdict(h) for h in (world.hypotheses if world else [])],
        findings=[asdict(f) for f in (world.findings if world else [])],
        global_step_analysis=session.global_step_analysis,
        flow_analysis=jsonable(flow) if flow is not None else None,
        synthesizer_iterations=s.iterations,
    )


def persist_report(session: AnalysisSession, report: DiagnosisReport) -> dict[str, Path | None]:
    payload = jsonable(report.to_dict())
    md_text = json_to_markdown(payload)
    bundle = write_report_bundle(
        session=session, payload=payload, markdown=md_text,
        base_name=f"reports/{report.report_id}",
    )
    _log.info("Report JSON: %s", bundle["json_path"])
    return {"report": bundle["json_path"], "markdown": bundle["markdown_path"]}
