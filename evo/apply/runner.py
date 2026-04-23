from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from evo.apply import opencode as oc
from evo.apply.errors import ApplyError
from evo.apply.git_workspace import GitWorkspace
from evo.apply.tests import TestOutcome, run_tests
from evo.harness.plan import StopRequested
from evo.runtime.config import EvoConfig

_NO_CHANGES_FEEDBACK = (
    '上一轮 opencode 未对任何 allowlist 中的文件做出修改。'
    '本轮必须实际改动至少一个允许文件，否则任务无法收尾。'
)

log = logging.getLogger('evo.apply')


@dataclass
class RoundResult:
    index: int
    files_changed: list[str] = field(default_factory=list)
    commit_sha: str | None = None
    test_passed: bool | None = None
    error: dict | None = None
    started_at: float = 0.0
    finished_at: float = 0.0


@dataclass
class ApplyResult:
    apply_id: str
    base_commit: str
    branch_name: str
    status: Literal['SUCCEEDED', 'FAILED']
    rounds: list[RoundResult] = field(default_factory=list)
    error: dict | None = None
    diff_index_path: Path | None = None


@dataclass
class ApplyOptions:
    max_rounds: int = 3
    test_command: tuple[str, ...] = ('bash', 'tests/run-all.sh')
    instruction: str = '根据 report 完成代码修改'
    opencode_options: oc.OpencodeOptions = field(default_factory=oc.OpencodeOptions)


def _check(token: Any | None, at: str | None = None) -> None:
    if token is not None and token.requested():
        raise StopRequested(at_step=at)


def _filter_actions(report: dict) -> list[dict]:
    actions = report.get('actions') or []
    if not isinstance(actions, list):
        raise ApplyError('REPORT_INVALID', 'report.actions must be a list',
                         {'actual_type': type(actions).__name__})
    return [a for a in actions
            if isinstance(a, dict) and a.get('code_map_in_scope')
            and a.get('code_map_target')]


def _build_allowlist(config: EvoConfig) -> list[str]:
    out: set[str] = set()
    for k in config.code_access.code_map.keys():
        if k:
            out.add(Path(k).as_posix())
    return sorted(out)


def _build_modification_plan(actions: list[dict]) -> list[dict]:
    return [{
        'id': str(a.get('id', '')),
        'title': str(a.get('title', '')),
        'rationale': str(a.get('rationale', '')),
        'suggested_changes': str(a.get('suggested_changes', '')),
        'priority': str(a.get('priority', '')),
        'files': [Path(str(a.get('code_map_target', ''))).as_posix()],
    } for a in actions]


def _build_prompt(instruction: str, plan: list[dict],
                  allowlist: list[str], prior_failure: str) -> str:
    parts: list[str] = [instruction.strip(), '']
    parts.append('允许修改的文件（严格遵守，禁止改动其它文件）：')
    parts.extend(f'- {f}' for f in allowlist)
    parts.append('')
    parts.append('修改计划（JSON）：')
    parts.append(json.dumps(plan, ensure_ascii=False, indent=2))
    if prior_failure.strip():
        parts.append('')
        parts.append('上一轮失败上下文（请据此调整本轮修改）：')
        parts.append(prior_failure.strip())
    return '\n'.join(parts) + '\n'


def _failure_context(files_changed: list[str],
                     test_outcome: TestOutcome) -> str:
    parts: list[str] = []
    if files_changed:
        parts.append('## 当前相对 baseline 已修改的文件')
        parts.extend(f'- {f}' for f in files_changed)
        parts.append('')
    tb = test_outcome.traceback_md_path
    if tb and tb.is_file():
        parts.append(tb.read_text(encoding='utf-8').strip())
    return '\n'.join(parts).strip()


def _exhausted_error(rounds: list[RoundResult], max_rounds: int) -> dict:
    last = rounds[-1] if rounds else None
    code = (last.error or {}).get('code') if last else None
    if code == 'OPENCODE_NO_CHANGES':
        return {
            'code': 'OPENCODE_NO_CHANGES',
            'kind': 'transient',
            'message': f'opencode 在 {max_rounds} 轮内均未产生文件变更',
            'details': {'rounds': max_rounds},
        }
    return {
        'code': 'MAX_ROUNDS_EXCEEDED',
        'kind': 'transient',
        'message': f'tests still failing after {max_rounds} round(s)',
        'details': {},
    }


def execute_apply(
    *,
    apply_id: str,
    report: dict,
    config: EvoConfig,
    workspace: GitWorkspace,
    options: ApplyOptions | None = None,
    cancel_token: Any | None = None,
    on_round: Callable[[RoundResult], None] | None = None,
    on_proc: Callable[[Any], None] | None = None,
) -> ApplyResult:
    options = options or ApplyOptions()
    actions = _filter_actions(report)
    if not actions:
        raise ApplyError('REPORT_INVALID', 'report has no in-scope actions')
    allowlist = _build_allowlist(config)
    if not allowlist:
        raise ApplyError('CODE_MAP_EMPTY', 'code_map is empty; nothing modifiable')

    binary = oc.preflight(options.opencode_options.binary,
                          auth_dir=config.storage.opencode_dir)
    workspace.ensure_bare()
    worktree, base_commit = workspace.create_worktree(apply_id)
    branch = GitWorkspace.branch_name(apply_id)

    apply_dir = config.storage.applies_dir / apply_id
    apply_dir.mkdir(parents=True, exist_ok=True)
    (apply_dir / 'input').mkdir(parents=True, exist_ok=True)
    plan = _build_modification_plan(actions)
    (apply_dir / 'input' / 'modification_plan.json').write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')

    rounds: list[RoundResult] = []
    prior_failure = ''
    final_status: Literal['SUCCEEDED', 'FAILED'] = 'FAILED'
    final_error: dict | None = None
    final_round_files: list[str] = []

    for i in range(1, options.max_rounds + 1):
        _check(cancel_token, at=f'round_{i:03d}.start')
        round_dir = apply_dir / 'rounds' / f'round_{i:03d}'
        if round_dir.exists():
            shutil.rmtree(round_dir)
        (round_dir / 'input').mkdir(parents=True, exist_ok=True)

        rr = RoundResult(index=i, started_at=time.time())
        prompt = _build_prompt(options.instruction, plan, allowlist, prior_failure)
        (round_dir / 'input' / 'prompt.txt').write_text(prompt, encoding='utf-8')

        try:
            outcome = oc.run_opencode(
                prompt, cwd=worktree,
                artifact_dir=round_dir / 'opencode',
                binary=binary, options=options.opencode_options,
                on_proc=on_proc,
            )
        except ApplyError as exc:
            rr.error = exc.to_payload()
            rr.finished_at = time.time()
            rounds.append(rr)
            if on_round:
                on_round(rr)
            final_error = rr.error
            break

        if outcome.returncode != 0:
            rr.error = {
                'code': 'OPENCODE_RUN_FAILED',
                'kind': 'transient',
                'message': f'opencode exit={outcome.returncode}',
                'details': {'last_error': outcome.last_error},
            }
            rr.finished_at = time.time()
            rounds.append(rr)
            if on_round:
                on_round(rr)
            final_error = rr.error
            break

        _check(cancel_token, at=f'round_{i:03d}.opencode_done')
        sha = workspace.commit_all(worktree, f'evo apply {apply_id} round {i}')
        rr.commit_sha = sha

        if sha is None:
            rr.test_passed = False
            rr.error = {
                'code': 'OPENCODE_NO_CHANGES',
                'kind': 'transient',
                'message': 'opencode 本轮未修改任何允许文件',
                'details': {},
            }
            rr.finished_at = time.time()
            rounds.append(rr)
            if on_round:
                on_round(rr)
            prior_failure = _NO_CHANGES_FEEDBACK
            continue

        diffs = workspace.diff(worktree, base_commit)
        rr.files_changed = [d.path for d in diffs]
        final_round_files = rr.files_changed

        _check(cancel_token, at=f'round_{i:03d}.diff_done')
        test_outcome = run_tests(worktree, round_dir / 'tests',
                                 command=options.test_command,
                                 on_proc=on_proc)
        rr.test_passed = test_outcome.passed
        rr.finished_at = time.time()
        rounds.append(rr)
        if on_round:
            on_round(rr)

        if test_outcome.passed:
            final_status = 'SUCCEEDED'
            break
        prior_failure = _failure_context(rr.files_changed, test_outcome)
    else:
        final_error = _exhausted_error(rounds, options.max_rounds)

    diff_index_path: Path | None = None
    if final_status == 'SUCCEEDED':
        from evo.service.diff_map import write_diff_map
        diff_index_path = write_diff_map(
            workspace=workspace, apply_id=apply_id,
            worktree=worktree, base_commit=base_commit,
            out_dir=config.storage.diffs_dir,
        )

    return ApplyResult(
        apply_id=apply_id,
        base_commit=base_commit,
        branch_name=branch,
        status=final_status,
        rounds=rounds,
        error=final_error,
        diff_index_path=diff_index_path,
    )
