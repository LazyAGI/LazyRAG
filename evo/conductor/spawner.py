from __future__ import annotations

from typing import Any

from evo.agents.critic import run_critic
from evo.agents.researcher import run_researcher
from evo.harness.executor import SessionAwareExecutor
from evo.runtime.session import AnalysisSession


def _dispatch(session: AnalysisSession, action: dict[str, Any]) -> Any:
    kind = action.get("kind")
    world = session.world_store.world if session.world_store else None
    if world is None:
        return None
    if kind == "research":
        h = next((h for h in world.hypotheses
                  if h.id == action.get("hypothesis_id")), None)
        return run_researcher(session, h) if h else None
    if kind == "critic":
        f = next((f for f in world.findings
                  if f.id == action.get("finding_id")), None)
        return run_critic(session, f) if f else None
    return None


def execute_batch(session: AnalysisSession, actions: list[dict[str, Any]],
                  max_workers: int = 4) -> list[Any]:
    if not actions:
        return []
    with SessionAwareExecutor(max_workers=max(1, max_workers)) as ex:
        futures = [ex.submit(_dispatch, session, a) for a in actions]
        return [f.result() for f in futures]
