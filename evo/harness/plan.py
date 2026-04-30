from __future__ import annotations
import logging
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from evo.runtime.session import AnalysisSession
class CancelTokenProto(Protocol):
    def requested(self) -> bool:
        ...
class StopRequested(Exception):
    def __init__(self, at_step: str | None=None) -> None:
        self.at_step = at_step
        super().__init__(f'stop requested at {at_step}')
@dataclass
class StepContext:
    session: AnalysisSession
    _results: dict[str, Any] = field(default_factory=dict)
    def get(self, step_name: str, default: Any=None) -> Any:
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
    description: str = ''
    always_run: bool = False
@dataclass
class StepOutcome:
    name: str
    status: str
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
        return [o.name for o in self.outcomes if o.status in ('ok', 'resumed')]
    @property
    def failed(self) -> list[StepOutcome]:
        return [o for o in self.outcomes if o.status == 'failed']
    def get(self, step_name: str) -> Any:
        for o in self.outcomes:
            if o.name == step_name and o.status in ('ok', 'resumed'):
                return o.value
        return None
def _checkpoints_dir(session: AnalysisSession) -> Path:
    p = session.config.storage.runs_dir / session.run_id / 'steps'
    p.mkdir(parents=True, exist_ok=True)
    return p
def _ckpt_path(steps_dir: Path, name: str) -> Path:
    return steps_dir / f'{name}.pickle'
class Plan:
    def __init__(self, steps: list[Step], *, logger: logging.Logger | None=None, before_step: Callable[[str, StepContext], None] | None=None) -> None:
        self.steps = steps
        self._log = logger or logging.getLogger('evo.harness.plan')
        self._before_step = before_step
    def run(self, session: AnalysisSession, *, cancel_token: CancelTokenProto | None=None) -> PlanResult:
        ctx = StepContext(session=session)
        steps_dir = _checkpoints_dir(session)
        start = time.time()
        outcomes: list[StepOutcome] = []
        fatal = False
        optional_by_name = {s.name: s.optional for s in self.steps}
        def _abort_check(step_name: str) -> None:
            if cancel_token is not None and cancel_token.requested():
                raise StopRequested(at_step=step_name)
        for step in self.steps:
            _abort_check(step.name)
            if self._before_step is not None:
                self._before_step(step.name, ctx)
                _abort_check(step.name)
            ckpt = _ckpt_path(steps_dir, step.name)
            if ckpt.exists():
                value = pickle.loads(ckpt.read_bytes())
                ctx._results[step.name] = value
                session.mark_stage(step.name)
                outcomes.append(StepOutcome(step.name, 'resumed', 0.0, value=value))
                self._log.info('Step %s resumed from checkpoint', step.name)
                continue
            if fatal and (not step.always_run):
                outcomes.append(StepOutcome(step.name, 'skipped', 0.0, error='prior fatal failure'))
                continue
            if step.skip_if and step.skip_if(ctx):
                self._log.info('Step %s skipped by predicate', step.name)
                outcomes.append(StepOutcome(step.name, 'skipped', 0.0))
                continue
            t0 = time.time()
            try:
                self._log.info('Step %s start', step.name)
                value = step.fn(ctx)
                elapsed = time.time() - t0
                outcomes.append(StepOutcome(step.name, 'ok', elapsed, value=value))
                ctx._results[step.name] = value
                session.mark_stage(step.name)
                try:
                    ckpt.write_bytes(pickle.dumps(value))
                except Exception as exc:
                    self._log.warning('Step %s checkpoint failed: %s', step.name, exc)
                self._log.info('Step %s done in %.2fs', step.name, elapsed)
            except StopRequested:
                raise
            except Exception as exc:
                elapsed = time.time() - t0
                self._log.error('Step %s failed: %s', step.name, exc, exc_info=True)
                outcomes.append(StepOutcome(step.name, 'failed', elapsed, error=f'{type(exc).__name__}: {exc}'))
                if not step.optional:
                    fatal = True
        success = not any((o.status == 'failed' and (not optional_by_name.get(o.name, False)) for o in outcomes))
        return PlanResult(success=success, session=session, outcomes=outcomes, elapsed_seconds=time.time() - start)
