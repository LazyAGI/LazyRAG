from __future__ import annotations
import json
import time
from typing import Any
from evo.conductor.prompts import load as load_prompt
from evo.conductor.synthesis import VerifiedAction
from evo.harness.executor import SessionAwareExecutor
from evo.harness.react import LLMInvoker
from evo.harness.schemas import SCHEMAS
from evo.harness.structured import invoke_structured
from evo.runtime.session import AnalysisSession
from evo.utils import jsonable

VERIFIER_NAME = 'action_verifier'


def _gather_handles(session: AnalysisSession, action: VerifiedAction) -> list[dict[str, Any]]:
    if session.handle_store is None:
        return []
    out: list[dict[str, Any]] = []
    for h_id in action.evidence_handles:
        h = session.handle_store.get(h_id)
        if h is None:
            continue
        out.append({'handle': h.id, 'tool': h.tool, 'args': jsonable(h.args), 'result': jsonable(h.result)})
    return out


def _build_user(action: VerifiedAction, evidence: list[dict[str, Any]]) -> str:
    view = {
        'id': action.id,
        'title': action.title,
        'rationale': action.rationale,
        'suggested_changes': action.suggested_changes,
        'expected_impact_metric': action.expected_impact_metric,
        'expected_direction': action.expected_direction,
        'confidence': action.confidence,
        'evidence_handles': list(action.evidence_handles),
    }
    return (
        f'## Action\n{json.dumps(view, ensure_ascii=False, indent=2)}\n\n'
        '## Raw evidence (full HandleStore content)\n'
        f'{json.dumps(evidence, ensure_ascii=False, indent=2)}\n'
    )


def _clamp(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def run_action_verifier(session: AnalysisSession, action: VerifiedAction, *, llm: Any | None = None) -> VerifiedAction:
    t_start = time.monotonic()
    invoker = LLMInvoker(session=session, system_prompt=load_prompt('action_verifier'), llm=llm)
    user = _build_user(action, _gather_handles(session, action))
    parsed = invoke_structured(
        session, invoker, user, agent=f'{VERIFIER_NAME}:{action.id}', schema=SCHEMAS['action_verifier']
    )
    action.validity_score = _clamp(parsed.get('validity_score', 0.0))
    action.supporting_evidence = [str(s) for s in parsed.get('supporting_evidence', []) or []]
    action.contradicting_evidence = [str(s) for s in parsed.get('contradicting_evidence', []) or []]
    action.verifier_notes = [str(n) for n in parsed.get('notes', []) or []]
    session.telemetry.emit(
        'agent_run',
        agent=f'{VERIFIER_NAME}:{action.id}',
        perspective=VERIFIER_NAME,
        action_id=action.id,
        validity_score=action.validity_score,
        supporting=len(action.supporting_evidence),
        contradicting=len(action.contradicting_evidence),
        elapsed_s=round(time.monotonic() - t_start, 4),
    )
    return action


def verify_actions(
    session: AnalysisSession, actions: list[VerifiedAction], *, max_workers: int = 4
) -> list[VerifiedAction]:
    if not actions:
        return actions
    with SessionAwareExecutor(max_workers=max(1, max_workers)) as ex:
        futures = [ex.submit(run_action_verifier, session, a) for a in actions]
        return [f.result() for f in futures]
