from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from evo.chat_runner import ChatInstance, ChatRegistry, ChatRunner
from evo.providers import EvalProvider
from evo.runtime.fs import atomic_write as _atomic_write
from evo.service.thread_workspace import EventLog, ThreadWorkspace

from .comparator import VerdictPolicy, compare_evals, judge_verdict

PHASES: tuple[str, ...] = (
    'launch_chat', 'run_eval', 'compare', 'persist',
)


@dataclass
class AbtestInputs:
    abtest_id: str
    thread_id: str
    apply_id: str
    baseline_eval_id: str
    dataset_id: str
    apply_worktree: Path
    eval_options: dict = field(default_factory=dict)
    policy: VerdictPolicy = field(default_factory=VerdictPolicy)
    judge_label: str = 'ab'


@dataclass
class AbtestResult:
    status: str
    verdict: str | None
    summary: dict | None
    candidate_chat_id: str | None
    new_eval_id: str | None
    error: str | None = None


def execute_abtest(*,
                   inputs: AbtestInputs,
                   workspace: ThreadWorkspace,
                   log: EventLog,
                   chat_runner: ChatRunner,
                   chat_registry: ChatRegistry,
                   eval_provider: EvalProvider,
                   cancel: Callable[[], bool] = lambda: False) -> AbtestResult:
    actor = f'abtest:{inputs.abtest_id}'
    state_path = workspace.abtest_dir(inputs.abtest_id) / 'phase.json'
    state = _load_state(state_path)
    state.setdefault('completed', [])
    state.setdefault('candidate_chat_id', None)
    state.setdefault('new_eval_id', None)

    candidate: ChatInstance | None = None
    if state['candidate_chat_id']:
        candidate = chat_registry.get(state['candidate_chat_id'])
    ctx = _Ctx(inputs, workspace, log, chat_runner, chat_registry,
               eval_provider, state, candidate)

    try:
        for phase in PHASES:
            if cancel():
                _save_state(state_path, state)
                return AbtestResult('cancelled', None, None,
                                    state['candidate_chat_id'],
                                    state['new_eval_id'])
            if phase in state['completed']:
                continue
            log.append(actor, 'phase.start', {'phase': phase})
            _PHASES_FN[phase](ctx)
            state['completed'].append(phase)
            _save_state(state_path, state)
            log.append(actor, 'phase.completed', {'phase': phase})
    except Exception as exc:
        log.append(actor, 'failed', {'phase': phase, 'error': str(exc)})
        if ctx.candidate is not None and 'persist' not in state['completed']:
            chat_runner.stop(ctx.candidate.chat_id)
            chat_registry.purge(ctx.candidate.chat_id)
        return AbtestResult('failed', None, state.get('summary'),
                            None, state.get('new_eval_id'), error=str(exc))

    summary = state.get('summary')
    return AbtestResult('succeeded', (summary or {}).get('verdict'),
                        summary, state['candidate_chat_id'],
                        state['new_eval_id'])


# --- internals --------------------------------------------------------------


@dataclass
class _Ctx:
    inputs: AbtestInputs
    ws: ThreadWorkspace
    log: EventLog
    runner: ChatRunner
    registry: ChatRegistry
    provider: EvalProvider
    state: dict
    candidate: ChatInstance | None


def _phase_launch_chat(c: _Ctx) -> None:
    if c.candidate is None or c.candidate.status != 'healthy':
        c.candidate = c.runner.launch(
            source_dir=c.inputs.apply_worktree,
            label=c.inputs.judge_label,
            owner_thread_id=c.inputs.thread_id,
        )
        c.registry.register(c.candidate)
    c.state['candidate_chat_id'] = c.candidate.chat_id


def _phase_run_eval(c: _Ctx) -> None:
    report = c.provider.run_eval(
        dataset_id=c.inputs.dataset_id,
        target_chat_url=c.candidate.base_url,
        options=c.inputs.eval_options,
    )
    eval_id = report.get('report_id') or f'cand-{c.inputs.abtest_id}'
    report['report_id'] = eval_id
    c.state['new_eval_id'] = eval_id
    _atomic_write(c.ws.eval_path(eval_id),
                   json.dumps(report, ensure_ascii=False, indent=2))


def _phase_compare(c: _Ctx) -> None:
    base_path = c.ws.eval_path(c.inputs.baseline_eval_id)
    if not base_path.exists():
        _atomic_write(base_path, json.dumps(c.provider.get_eval_report(
            c.inputs.baseline_eval_id), ensure_ascii=False, indent=2))
    base = json.loads(base_path.read_text(encoding='utf-8'))
    new = json.loads(c.ws.eval_path(c.state['new_eval_id']).read_text(encoding='utf-8'))
    diff = compare_evals(base, new, primary_metric=c.inputs.policy.primary_metric)
    diff.update(judge_verdict(diff, c.inputs.policy))
    c.state['summary'] = diff


def _phase_persist(c: _Ctx) -> None:
    out_dir = c.ws.abtest_dir(c.inputs.abtest_id)
    summary = c.state.get('summary') or {}
    _atomic_write(out_dir / 'summary.json',
                  json.dumps(summary, ensure_ascii=False, indent=2))
    _atomic_write(out_dir / 'summary.md', _summary_markdown(summary, c.inputs))


_PHASES_FN: dict[str, Callable[[_Ctx], None]] = {
    'launch_chat': _phase_launch_chat,
    'run_eval':    _phase_run_eval,
    'compare':     _phase_compare,
    'persist':     _phase_persist,
}


# --- IO --------------------------------------------------------------------

def _load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def _save_state(path: Path, state: dict) -> None:
    state['_updated_at'] = time.time()
    _atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2,
                                    default=str))


def _summary_markdown(summary: dict, inputs: AbtestInputs) -> str:
    if not summary:
        return f'# abtest {inputs.abtest_id}\n\n(no summary)\n'
    lines = [
        f'# abtest {inputs.abtest_id}', '',
        f'- baseline: `{inputs.baseline_eval_id}`',
        f'- dataset: `{inputs.dataset_id}`',
        f'- apply: `{inputs.apply_id}`',
        f'- verdict: **{summary.get("verdict")}**',
        f'- aligned cases: {summary.get("aligned_cases")}',
        '', '## metrics', '',
        '| metric | mean A | mean B | Δmean | win_rate B | sign p |',
        '| --- | --- | --- | --- | --- | --- |',
    ]
    for m, info in (summary.get('metrics') or {}).items():
        lines.append(f"| {m} | {info.get('mean_a')} | {info.get('mean_b')} | "
                     f"{info.get('delta_mean')} | {info.get('win_rate_b')} | "
                     f"{info.get('sign_p')} |")
    top = summary.get('top_diff_cases') or []
    if top:
        lines += ['', '## top diffs', '',
                  '| case | a | b | Δ |', '| --- | --- | --- | --- |']
        for row in top:
            lines.append(f"| {row['case_key']} | {row['a']} | {row['b']} | {row['delta']} |")
    lines += ['', '## reasons', '']
    for r in summary.get('reasons', []):
        lines.append(f'- {r}')
    return '\n'.join(lines) + '\n'
