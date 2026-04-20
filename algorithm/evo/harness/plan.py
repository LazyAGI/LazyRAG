from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from evo.runtime.session import AnalysisSession


@dataclass
class StepContext:
    session: AnalysisSession
    _results: dict[str, Any] = field(default_factory=dict)

    def get(self, step_name: str, default: Any = None) -> Any:
        return self._results.get(step_name, default)

    def require(self, step_name: str) -> Any:
        if step_name not in self._results:
            raise KeyError(f"Step '{step_name}' has no recorded result.")
        return self._results[step_name]

    @property
    def results(self) -> dict[str, Any]:
        return dict(self._results)


StepFn = Callable[[StepContext], Any]
Predicate = Callable[[StepContext], bool]


@dataclass
class Step:
    name: str
    fn: StepFn
    skip_if: Predicate | None = None
    optional: bool = False
    description: str = ""
    always_run: bool = False


@dataclass
class StepOutcome:
    name: str
    status: str  # "ok" | "skipped" | "failed"
    elapsed_seconds: float
    value: Any = None
    error: str | None = None


@dataclass
class PlanResult:
    success: bool
    session: AnalysisSession
    outcomes: list[StepOutcome] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def completed(self) -> list[str]:
        return [o.name for o in self.outcomes if o.status == "ok"]

    @property
    def failed(self) -> list[StepOutcome]:
        return [o for o in self.outcomes if o.status == "failed"]

    def get(self, step_name: str) -> Any:
        for o in self.outcomes:
            if o.name == step_name and o.status == "ok":
                return o.value
        return None


class Plan:
    def __init__(self, steps: list[Step], *, logger: logging.Logger | None = None) -> None:
        self.steps = steps
        self._log = logger or logging.getLogger("evo.harness.plan")

    def run(self, session: AnalysisSession) -> PlanResult:
        ctx = StepContext(session=session)
        start = time.time()
        outcomes: list[StepOutcome] = []
        fatal = False
        optional_by_name = {s.name: s.optional for s in self.steps}

        for step in self.steps:
            if fatal and not step.always_run:
                outcomes.append(StepOutcome(step.name, "skipped", 0.0,
                                            error="prior fatal failure"))
                continue
            if step.skip_if and step.skip_if(ctx):
                self._log.info("Step %s skipped by predicate", step.name)
                outcomes.append(StepOutcome(step.name, "skipped", 0.0))
                continue
            t0 = time.time()
            try:
                self._log.info("Step %s start", step.name)
                value = step.fn(ctx)
                elapsed = time.time() - t0
                outcomes.append(StepOutcome(step.name, "ok", elapsed, value=value))
                ctx._results[step.name] = value
                session.mark_stage(step.name)
                self._log.info("Step %s done in %.2fs", step.name, elapsed)
            except Exception as exc:
                elapsed = time.time() - t0
                self._log.error("Step %s failed: %s", step.name, exc, exc_info=True)
                outcomes.append(StepOutcome(step.name, "failed", elapsed,
                                            error=f"{type(exc).__name__}: {exc}"))
                if not step.optional:
                    fatal = True

        success = not any(
            o.status == "failed" and not optional_by_name.get(o.name, False)
            for o in outcomes
        )
        return PlanResult(success=success, session=session, outcomes=outcomes,
                          elapsed_seconds=time.time() - start)
