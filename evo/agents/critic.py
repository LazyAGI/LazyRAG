from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from evo.conductor.prompts import load as load_prompt
from evo.conductor.world_model import Finding, WorldModel
from evo.harness.react import LLMInvoker
from evo.harness.schemas import SCHEMAS
from evo.harness.structured import invoke_structured
from evo.runtime.session import AnalysisSession
from evo.utils import coerce_confidence, jsonable

CRITIC_NAME = "critic"
_VALID_STATUS = ("approved", "needs_revision")


@dataclass
class CriticVerdict:
    finding_id: str
    status: Literal["approved", "needs_revision"]
    challenges: list[dict[str, Any]] = field(default_factory=list)
    approved_confidence: float | None = None


def _gather_evidence(session: AnalysisSession,
                     finding: Finding) -> list[dict[str, Any]]:
    if session.handle_store is None:
        return []
    out: list[dict[str, Any]] = []
    for h_id in finding.evidence_handles:
        h = session.handle_store.get(h_id)
        if h is None:
            continue
        out.append({"handle": h.id, "tool": h.tool,
                    "args": jsonable(h.args), "result": jsonable(h.result)})
    return out


def _build_user(finding: Finding,
                evidence: list[dict[str, Any]]) -> str:
    finding_view = {
        "id": finding.id, "claim": finding.claim, "verdict": finding.verdict,
        "confidence": finding.confidence,
        "suggested_action": finding.suggested_action,
        "evidence_handles": list(finding.evidence_handles),
    }
    return (
        f"## Finding\n{json.dumps(finding_view, ensure_ascii=False, indent=2)}\n\n"
        "## Raw evidence (full HandleStore content)\n"
        f"{json.dumps(evidence, ensure_ascii=False, indent=2)}\n"
    )


def run_critic(session: AnalysisSession, finding: Finding,
               *, llm: Any | None = None) -> CriticVerdict:
    t_start = time.monotonic()
    invoker = LLMInvoker(session=session, system_prompt=load_prompt("critic"), llm=llm)
    user = _build_user(finding, _gather_evidence(session, finding))
    parsed = invoke_structured(
        session, invoker, user,
        agent=f"{CRITIC_NAME}:{finding.id}",
        schema=SCHEMAS["critic"],
    )
    status = str(parsed.get("verdict", "needs_revision"))
    if status not in _VALID_STATUS:
        status = "needs_revision"
    approved_conf = parsed.get("approved_confidence")
    verdict = CriticVerdict(
        finding_id=finding.id, status=status,
        challenges=list(parsed.get("challenges", []) or []),
        approved_confidence=(coerce_confidence(approved_conf)
                             if approved_conf is not None else None),
    )
    if session.world_store is not None:
        session.world_store.update(lambda w: _record(w, verdict))
    session.telemetry.emit(
        "agent_run", agent=f"{CRITIC_NAME}:{finding.id}",
        perspective=CRITIC_NAME, finding_id=finding.id,
        status=verdict.status, challenges=len(verdict.challenges),
        elapsed_s=round(time.monotonic() - t_start, 4),
    )
    return verdict


def _challenge_text(c: Any) -> str:
    if isinstance(c, dict):
        return str(c.get("issue") or c.get("note") or c.get("text") or "")
    if isinstance(c, str):
        return c
    return str(c)


def _record(world: WorldModel, v: CriticVerdict) -> None:
    for f in world.findings:
        if f.id != v.finding_id:
            continue
        f.critic_status = "approved" if v.status == "approved" else "needs_revision"
        f.critic_notes = [t for t in (_challenge_text(c) for c in v.challenges) if t]
        if v.approved_confidence is not None:
            f.confidence = v.approved_confidence
        break
