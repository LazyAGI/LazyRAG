from __future__ import annotations

import json
import time
from typing import Any

from evo.conductor.prompts import load as load_prompt
from evo.conductor.world_model import Hypothesis, WorldModel
from evo.harness.react import LLMInvoker
from evo.harness.schemas import SCHEMAS
from evo.harness.structured import invoke_structured
from evo.runtime.session import AnalysisSession
from evo.runtime.thresholds import METRIC_DIRECTION
from evo.utils import coerce_confidence

INDEXER_NAME = "indexer"
_JUDGE_METRICS = ("answer_correctness", "context_recall", "doc_recall", "faithfulness")


def _avg_judge(session: AnalysisSession) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in _JUDGE_METRICS:
        vals = [getattr(j, m, None) for j in session.parsed_judge.values()]
        nums = [float(v) for v in vals if isinstance(v, (int, float))]
        if nums:
            out[m] = round(sum(nums) / len(nums), 4)
    return out


def _build_input(session: AnalysisSession) -> dict[str, Any]:
    cg = session.clustering_global
    fa = session.flow_analysis
    return {
        "pipeline": list(session.trace_meta.pipeline),
        "total_cases": len(session.parsed_judge),
        "avg_judge": _avg_judge(session),
        "step_metrics": {
            step: stats.get("stats", stats)
            for step, stats in session.global_step_analysis.items()
        },
        "metric_directions": {
            m: d for m, d in METRIC_DIRECTION.items()
            if any(m in stats.get("stats", stats)
                   for stats in session.global_step_analysis.values()
                   if isinstance(stats, dict))
            or m in _JUDGE_METRICS
        },
        "clusters": [
            {"id": cs.cluster_id, "size": cs.size,
             "score_stats": cs.score_stats,
             "top_features": dict(list(cs.top_feature_deltas.items())[:8])}
            for cs in (cg.cluster_summaries if cg else [])
        ],
        "flow": {
            "transitions": [
                {"from": t.from_step, "to": t.to_step, "type": t.type,
                 "entropy_change": t.entropy_change, "nmi": t.nmi}
                for t in (fa.transition_analysis if fa else [])
            ],
            "critical_steps": list(fa.critical_steps) if fa else [],
        },
    }


def _normalize_hypothesis(h: Any) -> dict[str, Any] | None:
    if isinstance(h, dict):
        return h
    if isinstance(h, str) and h.strip():
        return {"claim": h.strip()}
    return None


def _append_hypotheses(world: WorldModel, hyps: list[Any]) -> None:
    seen = {h.id for h in world.hypotheses}
    seq = len(world.hypotheses)
    for raw in hyps:
        h = _normalize_hypothesis(raw)
        if h is None:
            continue
        seq += 1
        hid = h.get("id") or f"H{seq:03d}"
        if hid in seen:
            continue
        seen.add(hid)
        paths = h.get("investigation_paths") or []
        if not isinstance(paths, list):
            paths = [paths]
        world.hypotheses.append(Hypothesis(
            id=hid,
            claim=str(h.get("claim", "")),
            category=str(h.get("category", "")),
            status="proposed",
            confidence=coerce_confidence(h.get("confidence")),
            evidence_handles=[],
            investigation_paths=[str(p) for p in paths],
            source=INDEXER_NAME,
        ))


def run_indexer(session: AnalysisSession, *, llm: Any | None = None) -> dict[str, Any]:
    t_start = time.monotonic()
    payload = _build_input(session)
    invoker = LLMInvoker(session=session, system_prompt=load_prompt("indexer"), llm=llm)
    parsed = invoke_structured(
        session, invoker,
        json.dumps(payload, ensure_ascii=False, indent=2),
        agent=INDEXER_NAME, schema=SCHEMAS["indexer"],
        cache_key=f"indexer:{session.run_id}",
    )
    hypotheses = parsed.get("hypotheses", []) or []
    open_questions = [str(q) for q in (parsed.get("open_questions") or []) if str(q)]
    if session.world_store is not None and (hypotheses or open_questions):
        def _apply(world: WorldModel) -> None:
            if hypotheses:
                _append_hypotheses(world, hypotheses)
            if open_questions:
                seen = set(world.open_questions)
                for q in open_questions:
                    if q not in seen:
                        world.open_questions.append(q)
                        seen.add(q)
        session.world_store.update(_apply)
    session.telemetry.emit(
        "agent_run", agent=INDEXER_NAME, perspective=INDEXER_NAME,
        hypothesis_count=len(hypotheses), open_questions=len(open_questions),
        elapsed_s=round(time.monotonic() - t_start, 4),
    )
    return parsed
