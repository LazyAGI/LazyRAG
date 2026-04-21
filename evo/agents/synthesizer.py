from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from evo.conductor.prompts import load as load_prompt
from evo.conductor.spawner import execute_batch
from evo.conductor.synthesis import (
    DIRECTION_VALUES, PRIORITY_ORDER, SynthesisResult, VerifiedAction,
)
from evo.conductor.world_model import Hypothesis
from evo.harness.react import LLMInvoker
from evo.harness.schemas import SCHEMAS
from evo.harness.structured import invoke_structured
from evo.runtime.code_config import code_context_dict
from evo.runtime.session import AnalysisSession

SYNTHESIZER_NAME = "synthesizer"
_MAX_GAP_HYPOTHESES = 4


def run_synthesizer(session: AnalysisSession, *, llm: Any | None = None) -> SynthesisResult:
    t_start = time.monotonic()
    parsed = _synthesize_once(session, iteration=0, llm=llm)
    iterations = 1
    if parsed.get("gap_hypotheses"):
        new_hids = _append_gaps_and_research(session, parsed["gap_hypotheses"])
        if new_hids:
            parsed = _synthesize_once(session, iteration=1, llm=llm)
            iterations = 2
    actions = [_to_action(a, session) for a in parsed.get("actions", []) or []]
    actions = [a for a in actions if a is not None]
    _annotate_with_code_map(actions, session)
    result = SynthesisResult(
        summary=str(parsed.get("summary", "")),
        guidance=str(parsed.get("guidance", "")),
        actions=actions,
        open_gaps=[str(g) for g in parsed.get("open_gaps", []) or []],
        iterations=iterations,
    )
    session.telemetry.emit(
        "agent_run", agent=SYNTHESIZER_NAME, perspective=SYNTHESIZER_NAME,
        action_count=len(result.actions), open_gaps=len(result.open_gaps),
        iterations=result.iterations,
        elapsed_s=round(time.monotonic() - t_start, 4),
    )
    return result


def _synthesize_once(session: AnalysisSession, *, iteration: int,
                     llm: Any | None) -> dict[str, Any]:
    invoker = LLMInvoker(session=session, system_prompt=load_prompt("synthesizer"), llm=llm)
    user = json.dumps(_world_summary(session, iteration), ensure_ascii=False, indent=2)
    return invoke_structured(
        session, invoker, user,
        agent=SYNTHESIZER_NAME, schema=SCHEMAS["synthesizer"],
    )


def _world_summary(session: AnalysisSession, iteration: int) -> dict[str, Any]:
    w = session.world_store.world if session.world_store else None
    code_ctx = code_context_dict(session.config.code_access)
    if w is None:
        return {"iteration": iteration, "hypotheses": [], "findings": [],
                "open_questions": [], "code_context": code_ctx}
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for h in w.hypotheses:
        by_cat[h.category or "uncategorized"].append({
            "id": h.id, "claim": h.claim, "status": h.status,
            "confidence": h.confidence, "source": h.source,
        })
    findings = [
        {"id": f.id, "hypothesis_id": f.hypothesis_id, "claim": f.claim,
         "verdict": f.verdict, "confidence": f.confidence,
         "critic_status": f.critic_status, "critic_notes": list(f.critic_notes),
         "evidence_handles": list(f.evidence_handles),
         "suggested_action": f.suggested_action}
        for f in w.findings if f.verdict in ("confirmed", "inconclusive")
    ]
    return {
        "iteration": iteration + 1,
        "is_final_round": iteration + 1 >= 2,
        "code_context": code_ctx,
        "hypotheses_by_category": dict(by_cat),
        "findings": findings,
        "open_questions": list(w.open_questions),
    }


def _append_gaps_and_research(session: AnalysisSession,
                              gap_hypotheses: list[dict[str, Any]]) -> list[str]:
    new_hids: list[str] = []

    def _append(world):
        for gh in (gap_hypotheses or [])[:_MAX_GAP_HYPOTHESES]:
            existing = {h.id for h in world.hypotheses}
            base = gh.get("id") or f"GH{len(world.hypotheses) + 1:03d}"
            hid = base
            n = 1
            while hid in existing:
                n += 1
                hid = f"{base}_{n}"
            world.hypotheses.append(Hypothesis(
                id=hid, claim=str(gh.get("claim", "")),
                category=str(gh.get("category", "")), status="proposed",
                investigation_paths=[str(p) for p in gh.get("investigation_paths", [])],
                source=SYNTHESIZER_NAME,
            ))
            new_hids.append(hid)

    session.world_store.update(_append)
    if not new_hids:
        return new_hids
    execute_batch(session,
                  [{"kind": "research", "hypothesis_id": h} for h in new_hids],
                  max_workers=4)
    pending = [f.id for f in session.world_store.world.findings
               if f.hypothesis_id in new_hids and f.critic_status == "pending"]
    if pending:
        execute_batch(session,
                      [{"kind": "critic", "finding_id": fid} for fid in pending],
                      max_workers=4)
    return new_hids


def _to_action(raw: Any, session: AnalysisSession) -> VerifiedAction | None:
    if not isinstance(raw, dict):
        return None
    aid = str(raw.get("id") or "")
    if not aid:
        return None
    priority = str(raw.get("priority", "P2"))
    if priority not in PRIORITY_ORDER:
        priority = "P2"
    direction = str(raw.get("expected_direction", "+"))
    if direction not in DIRECTION_VALUES:
        direction = "+"
    try:
        confidence = float(raw.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    target = str(raw.get("code_map_target") or raw.get("target_file") or "")
    try:
        line = int(raw.get("target_line", 0) or 0)
    except (TypeError, ValueError):
        line = 0
    return VerifiedAction(
        id=aid,
        finding_id=str(raw.get("finding_id", "")),
        hypothesis_id=str(raw.get("hypothesis_id", "")),
        hypothesis_category=str(raw.get("hypothesis_category", "")),
        title=str(raw.get("title", "")),
        rationale=str(raw.get("rationale", "")),
        suggested_changes=str(raw.get("suggested_changes", "")),
        priority=priority,                                       # type: ignore[arg-type]
        expected_impact_metric=str(raw.get("expected_impact_metric", "")),
        expected_direction=direction,                            # type: ignore[arg-type]
        confidence=max(0.0, min(1.0, confidence)),
        evidence_handles=[str(h) for h in raw.get("evidence_handles", []) or []],
        code_map_target=target,
        target_step=str(raw.get("target_step", "")),
        target_line=line,
    )


_PATH_RE = re.compile(r"(?:\.{1,2}/)?[\w./\\\-]+\.\w+")


def _annotate_with_code_map(actions: list[VerifiedAction], session: AnalysisSession) -> None:
    cm = session.config.code_access.code_map
    cm_keys = {Path(p).resolve() for p in cm.keys()}
    cm_basenames = {Path(p).name: Path(p).resolve() for p in cm.keys()}
    if not cm_keys:
        for a in actions:
            a.code_map_in_scope = True
            a.code_map_warning = "code_map empty: scope check disabled"
        return
    basename_set = set(cm_basenames.keys())
    for a in actions:
        target = a.code_map_target.strip()
        if not target:
            target = (_guess_target(a.suggested_changes, basename_set)
                      or _guess_target(a.rationale, basename_set) or "")
            if target:
                a.code_map_target = target
        if not target:
            a.code_map_in_scope = False
            a.code_map_warning = "no explicit code_map target; falls outside modifiable scope"
            _demote(a, "missing target")
            continue
        try:
            t = Path(target).expanduser().resolve()
        except OSError:
            a.code_map_in_scope = False
            a.code_map_warning = f"unresolvable target: {target}"
            _demote(a, "unresolvable target")
            continue
        if t in cm_keys:
            a.code_map_in_scope = True
            a.code_map_warning = ""
        elif t.name in basename_set:
            a.code_map_target = str(cm_basenames[t.name])
            a.code_map_in_scope = True
            a.code_map_warning = ""
        else:
            a.code_map_in_scope = False
            a.code_map_warning = (
                f"target {target} is outside code_map "
                f"(modifiable: {sorted(basename_set)})"
            )
            _demote(a, "out of code_map")


def _demote(action: VerifiedAction, reason: str) -> None:
    if action.priority != "P2":
        prev = action.priority
        action.priority = "P2"
        suffix = f" [demoted {prev}->P2: {reason}]"
        action.code_map_warning = (action.code_map_warning + suffix).strip()


def _guess_target(text: str, cm_basenames: set[str]) -> str | None:
    if not text:
        return None
    for m in _PATH_RE.finditer(text):
        cand = m.group(0)
        if Path(cand).name in cm_basenames:
            return cand
    for name in cm_basenames:
        if name in text:
            return name
    return None
