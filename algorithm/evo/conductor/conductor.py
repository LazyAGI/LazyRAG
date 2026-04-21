from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from evo.conductor.prompts import load as load_prompt
from evo.conductor.spawner import execute_batch
from evo.harness.react import LLMInvoker
from evo.runtime.session import AnalysisSession
from evo.harness.schemas import SCHEMAS
from evo.harness.structured import invoke_structured

CONDUCTOR_NAME = "conductor"


@dataclass
class ConductorConfig:
    max_iterations: int = 8
    max_concurrent: int = 4
    max_actions_per_batch: int = 6
    max_research_per_hypothesis: int = 3


@dataclass
class ConductorRunResult:
    iterations: int
    converged: bool
    total_actions: int


class Conductor:
    def __init__(self, session: AnalysisSession,
                 cfg: ConductorConfig | None = None,
                 llm: Any | None = None) -> None:
        self.session = session
        self.cfg = cfg or ConductorConfig()
        self._invoker = LLMInvoker(
            session=session, system_prompt=load_prompt("conductor"), llm=llm,
        )
        self._research_count: dict[str, int] = {}
        self._log = session.logger("conductor")

    def run(self) -> ConductorRunResult:
        total = 0
        for it in range(self.cfg.max_iterations):
            self._tick(it)
            decision = self._plan(it)
            actions = self._filter(decision.get("actions") or [])
            self._log.info(
                "Conductor iter=%d done=%s actions_planned=%d actions_run=%d",
                it + 1, decision.get("done"), len(decision.get("actions") or []), len(actions),
            )
            if decision.get("done") and not actions:
                self._mark_converged()
                self._emit(it + 1, True, total)
                return ConductorRunResult(it + 1, True, total)
            if not actions:
                self._mark_converged()
                self._emit(it + 1, True, total)
                return ConductorRunResult(it + 1, True, total)
            execute_batch(self.session, actions, self.cfg.max_concurrent)
            total += len(actions)
        self._mark_converged()
        self._emit(self.cfg.max_iterations, False, total)
        return ConductorRunResult(self.cfg.max_iterations, False, total)

    def _plan(self, iteration: int) -> dict[str, Any]:
        snapshot = self._snapshot(iteration)
        user = json.dumps(snapshot, ensure_ascii=False, indent=2)
        return invoke_structured(
            self.session, self._invoker, user,
            agent=CONDUCTOR_NAME, schema=SCHEMAS["conductor"],
        ) or {"actions": [], "done": True}

    def _snapshot(self, iteration: int) -> dict[str, Any]:
        w = self.session.world_store.world
        return {
            "iteration": iteration + 1,
            "max_iterations": self.cfg.max_iterations,
            "hypotheses": [
                {"id": h.id, "claim": h.claim, "category": h.category,
                 "status": h.status, "confidence": h.confidence,
                 "investigation_paths": list(h.investigation_paths)}
                for h in w.hypotheses
            ],
            "findings": [
                {"id": f.id, "hypothesis_id": f.hypothesis_id, "verdict": f.verdict,
                 "critic_status": f.critic_status, "critic_notes": list(f.critic_notes)}
                for f in w.findings
            ],
            "open_questions": list(w.open_questions),
            "budget_remaining": self.cfg.max_iterations - iteration,
        }

    def _filter(self, raw_actions: list[Any]) -> list[dict[str, Any]]:
        clean: list[dict[str, Any]] = []
        for a in raw_actions[: self.cfg.max_actions_per_batch]:
            if not isinstance(a, dict) or "kind" not in a:
                continue
            kind = a["kind"]
            if kind == "research":
                hid = str(a.get("hypothesis_id", ""))
                used = self._research_count.get(hid, 0)
                if used >= self.cfg.max_research_per_hypothesis:
                    continue
                self._research_count[hid] = used + 1
            clean.append(a)
        return clean

    def _tick(self, it: int) -> None:
        if self.session.world_store is None:
            return
        self.session.world_store.update(
            lambda w: setattr(w, "iteration", it + 1),
        )

    def _mark_converged(self) -> None:
        if self.session.world_store is None:
            return
        self.session.world_store.update(
            lambda w: setattr(w, "status", "converged"),
        )

    def _emit(self, iterations: int, converged: bool, total: int) -> None:
        self.session.telemetry.emit(
            "agent_run", agent=CONDUCTOR_NAME, perspective=CONDUCTOR_NAME,
            iterations=iterations, converged=converged, total_actions=total,
        )
