from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from automation.opencode_adapter.errors import NO_CHANGE, AdapterError, OPENCODE_EXEC_FAILED
from automation.opencode_adapter.executor import (
    _artifact_base,
    _cleanup_artifacts,
    _coerce_mapping,
    _create_worktree,
    _display_artifacts_dir,
    _resolve_base_commit,
    _run_command,
    _validate_repo,
    _write_json,
    _write_text,
    execute,
)
from automation.opencode_adapter.types import (
    AdapterOutcome,
    ReportOutcome,
    ReportSummary,
    TaskExecutionResult,
    ValidationCheckResult,
    ValidationResult,
)


DEFAULT_VALIDATION_TIMEOUT_SECONDS = 300


def execute_report(payload: Mapping[str, Any]) -> ReportOutcome:
    report_id = 'report'
    repo_hint = ''
    artifact_base = _artifact_base(repo_hint)
    artifacts_dir = artifact_base / '.automation' / 'opencode' / 'report_report'
    relative_artifacts_dir = _display_artifacts_dir(artifact_base, artifacts_dir)

    try:
        input_payload = _coerce_mapping(payload, 'payload')
        repo_hint = str(input_payload.get('repo_path') or '').strip()
        artifact_base = _artifact_base(repo_hint)
        report = _extract_report(input_payload)
        report_id = str(report.get('report_id') or 'report').strip() or 'report'
        safe_report_id = _sanitize_identifier(report_id, fallback='report')
        artifacts_dir = artifact_base / '.automation' / 'opencode' / f'report_{safe_report_id}'
        relative_artifacts_dir = _display_artifacts_dir(artifact_base, artifacts_dir)

        _cleanup_artifacts(repo_hint, artifacts_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        _write_json(artifacts_dir / 'input.json', input_payload)

        repo_root = _validate_repo(repo_hint)
        base_ref = str(input_payload.get('base_ref') or 'HEAD').strip() or 'HEAD'
        base_commit = _resolve_base_commit(repo_root, base_ref)
        ordered_tasks = _order_tasks(_extract_tasks(report))
        opencode_options = _coerce_mapping(input_payload.get('opencode'), 'opencode', allow_none=True)
        staging_dir = artifacts_dir / 'worktree'
        _create_worktree(repo_root, base_commit, staging_dir)

        current_commit = base_commit
        task_results: List[TaskExecutionResult] = []
        task_statuses: Dict[str, str] = {}

        for task in ordered_tasks:
            task_id = str(task.get('task_id') or 'task').strip() or 'task'
            execution_task_id = _sanitize_identifier(f'{safe_report_id}_{task_id}', fallback='task')
            module = str(task.get('module') or '').strip()

            dependency_block = _dependency_block_reason(task, task_statuses)
            if dependency_block:
                blocked = _blocked_task_result(task_id, execution_task_id, module, dependency_block)
                task_results.append(blocked)
                task_statuses[task_id] = blocked['status']
                continue

            task_payload = _build_task_payload(
                report=report,
                task=task,
                repo_path=repo_root,
                base_ref=current_commit,
                opencode_options=opencode_options,
                execution_task_id=execution_task_id,
            )
            modify_result = execute(task_payload)
            validation_result = _empty_validation_result('Validation was not started.')
            extra_risk = ''
            status = 'FAILED'

            if modify_result['status'] == 'FAILED':
                validation_result = _empty_validation_result('Validation skipped because code modification failed.')
                extra_risk = 'The task did not produce an accepted patch.'
                status = 'FAILED'
            else:
                if modify_result['status'] == 'SUCCEEDED':
                    patch_path = repo_root / modify_result['artifacts_dir'] / 'diff.patch'
                    try:
                        _apply_patch_to_worktree(staging_dir, patch_path)
                    except AdapterError as exc:
                        validation_result = _empty_validation_result(
                            'Validation skipped because the generated patch could not be applied.'
                        )
                        _recreate_staging_worktree(repo_root, staging_dir, current_commit)
                        extra_risk = exc.message
                        status = 'FAILED'
                    else:
                        validation_result = _run_validation(task, staging_dir)
                        if validation_result['status'] == 'FAILED':
                            _recreate_staging_worktree(repo_root, staging_dir, current_commit)
                            extra_risk = (
                                'Validation failed; the generated patch was not promoted to the accepted state.'
                            )
                            status = 'FAILED'
                        else:
                            current_commit = _commit_worktree(staging_dir, execution_task_id)
                            status = 'SUCCEEDED' if validation_result['status'] == 'PASSED' else 'PARTIAL'
                else:
                    validation_result = _empty_validation_result(
                        'Validation skipped because OpenCode made no code changes.'
                    )
                    status = NO_CHANGE

            remaining_risks = _summarize_remaining_risks(
                task=task,
                modify_result=modify_result,
                validation_result=validation_result,
                extra_risk=extra_risk,
            )
            task_result: TaskExecutionResult = {
                'task_id': task_id,
                'execution_task_id': execution_task_id,
                'module': module,
                'status': status,
                'modify_result': modify_result,
                'validation_result': validation_result,
                'remaining_risks': remaining_risks,
            }
            task_results.append(task_result)
            task_statuses[task_id] = status

        cumulative_diff = _collect_cumulative_diff(staging_dir, base_commit, current_commit)
        _write_text(artifacts_dir / 'cumulative.diff.patch', cumulative_diff)
        summary = _build_report_summary(task_results)
        outcome: ReportOutcome = {
            'status': _overall_status(task_results),
            'report_id': report_id,
            'task_results': task_results,
            'summary': summary,
            'artifacts_dir': relative_artifacts_dir,
        }
        _persist_report_outcome(artifacts_dir, outcome)
        return outcome
    except AdapterError as exc:
        failed_summary: ReportSummary = {
            'total_tasks': 0,
            'succeeded': 0,
            'partial': 0,
            'failed': 1,
            'blocked': 0,
            'no_change': 0,
            'files_changed': [],
            'remaining_risks': [exc.message],
        }
        outcome = {
            'status': 'FAILED',
            'report_id': report_id,
            'task_results': [],
            'summary': failed_summary,
            'artifacts_dir': relative_artifacts_dir,
        }
        _persist_report_outcome(artifacts_dir, outcome)
        return outcome
    except Exception as exc:
        wrapped = AdapterError(
            OPENCODE_EXEC_FAILED,
            'unexpected report runner failure',
            {'error': str(exc)},
        )
        failed_summary = {
            'total_tasks': 0,
            'succeeded': 0,
            'partial': 0,
            'failed': 1,
            'blocked': 0,
            'no_change': 0,
            'files_changed': [],
            'remaining_risks': [wrapped.message],
        }
        outcome = {
            'status': 'FAILED',
            'report_id': report_id,
            'task_results': [],
            'summary': failed_summary,
            'artifacts_dir': relative_artifacts_dir,
        }
        _persist_report_outcome(artifacts_dir, outcome)
        return outcome


def _extract_report(input_payload: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    if 'report' in input_payload:
        report = _coerce_mapping(input_payload.get('report'), 'report')
    elif 'task_plans' in input_payload or 'report_id' in input_payload:
        report = input_payload
    else:
        raise AdapterError(OPENCODE_EXEC_FAILED, 'report payload is required', {'field': 'report'})
    if not isinstance(report.get('task_plans'), list):
        raise AdapterError(OPENCODE_EXEC_FAILED, 'report.task_plans must be a list', {'field': 'task_plans'})
    return report


def _extract_tasks(report: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    tasks: List[MutableMapping[str, Any]] = []
    for index, item in enumerate(report.get('task_plans') or []):
        if not isinstance(item, MutableMapping):
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'each task_plan must be an object',
                {'field': f'task_plans[{index}]', 'actual_type': type(item).__name__},
            )
        tasks.append(item)
    return tasks


def _order_tasks(tasks: Sequence[MutableMapping[str, Any]]) -> List[MutableMapping[str, Any]]:
    task_map: Dict[str, MutableMapping[str, Any]] = {}
    dependencies: Dict[str, Set[str]] = {}
    reverse_edges: Dict[str, Set[str]] = {}

    for task in tasks:
        task_id = str(task.get('task_id') or '').strip()
        if not task_id:
            raise AdapterError(OPENCODE_EXEC_FAILED, 'task_id is required for each task', {})
        if task_id in task_map:
            raise AdapterError(OPENCODE_EXEC_FAILED, 'duplicate task_id detected', {'task_id': task_id})
        task_map[task_id] = task
        dependencies[task_id] = set()
        reverse_edges[task_id] = set()

    for task_id, task in task_map.items():
        raw_dependencies = task.get('depends_on') or []
        if raw_dependencies and not isinstance(raw_dependencies, list):
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'depends_on must be a list',
                {'task_id': task_id, 'field': 'depends_on'},
            )
        for dependency in raw_dependencies:
            dependency_id = str(dependency).strip()
            if dependency_id not in task_map:
                raise AdapterError(
                    OPENCODE_EXEC_FAILED,
                    'depends_on references an unknown task',
                    {'task_id': task_id, 'depends_on': dependency_id},
                )
            dependencies[task_id].add(dependency_id)
            reverse_edges[dependency_id].add(task_id)

    ready = [task_id for task_id, deps in dependencies.items() if not deps]
    ordered: List[MutableMapping[str, Any]] = []

    while ready:
        ready.sort(key=lambda task_id: _task_sort_key(task_map[task_id]))
        current_id = ready.pop(0)
        ordered.append(task_map[current_id])
        for dependent in sorted(reverse_edges[current_id]):
            dependencies[dependent].discard(current_id)
            if not dependencies[dependent]:
                ready.append(dependent)

    if len(ordered) != len(tasks):
        unresolved = sorted(task_id for task_id, deps in dependencies.items() if deps)
        raise AdapterError(OPENCODE_EXEC_FAILED, 'task dependency cycle detected', {'tasks': unresolved})
    return ordered


def _task_sort_key(task: Mapping[str, Any]) -> Tuple[int, int, str]:
    priority = task.get('priority')
    risk = task.get('risk')
    try:
        normalized_priority = int(priority)
    except (TypeError, ValueError):
        normalized_priority = 10**6
    try:
        normalized_risk = int(risk)
    except (TypeError, ValueError):
        normalized_risk = -1
    task_id = str(task.get('task_id') or '')
    return normalized_priority, -normalized_risk, task_id


def _build_task_payload(
    *,
    report: Mapping[str, Any],
    task: MutableMapping[str, Any],
    repo_path: Path,
    base_ref: str,
    opencode_options: MutableMapping[str, Any],
    execution_task_id: str,
) -> Dict[str, Any]:
    task_plan = dict(task)
    task_plan['task_id'] = execution_task_id
    task_plan.setdefault('report_id', report.get('report_id'))
    if report.get('instruction') is not None:
        task_plan['instruction'] = report.get('instruction')
    if report.get('constraints') is not None:
        task_plan['constraints'] = report.get('constraints')
    if report.get('top_issue') is not None:
        task_plan['top_issue'] = report.get('top_issue')

    payload: Dict[str, Any] = {
        'repo_path': str(repo_path),
        'base_ref': base_ref,
        'task_plan': task_plan,
        'opencode': dict(opencode_options),
    }

    code_context = _build_code_context(task)
    if code_context:
        payload['code_context'] = code_context
    return payload


def _build_code_context(task: Mapping[str, Any]) -> Dict[str, Any]:
    context = dict(_coerce_mapping(task.get('code_context'), 'task.code_context', allow_none=True))
    files: List[str] = []
    seen: Set[str] = set()
    for index, target in enumerate(task.get('change_targets') or []):
        if not isinstance(target, Mapping):
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'each change_target must be an object',
                {'field': f'change_targets[{index}]', 'actual_type': type(target).__name__},
            )
        file_path = str(target.get('file') or '').strip()
        if file_path and file_path not in seen:
            seen.add(file_path)
            files.append(file_path)

    if files:
        context.setdefault('target_file', files[0])
        existing_related = context.get('related_files') or []
        if existing_related and not isinstance(existing_related, list):
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'task.code_context.related_files must be a list',
                {'field': 'task.code_context.related_files'},
            )
        related_files = [str(item).strip() for item in existing_related if str(item).strip()]
        for file_path in files[1:]:
            if file_path not in related_files and file_path != context.get('target_file'):
                related_files.append(file_path)
        if related_files:
            context['related_files'] = related_files

    return context


def _dependency_block_reason(task: Mapping[str, Any], task_statuses: Mapping[str, str]) -> str:
    for dependency in task.get('depends_on') or []:
        dependency_id = str(dependency).strip()
        dependency_status = task_statuses.get(dependency_id, '')
        if dependency_status in {'FAILED', 'BLOCKED'}:
            return f'Task dependency {dependency_id} did not complete successfully.'
    return ''


def _blocked_task_result(task_id: str, execution_task_id: str, module: str, reason: str) -> TaskExecutionResult:
    return {
        'task_id': task_id,
        'execution_task_id': execution_task_id,
        'module': module,
        'status': 'BLOCKED',
        'modify_result': None,
        'validation_result': _empty_validation_result(f'Validation skipped because the task was blocked: {reason}'),
        'remaining_risks': [reason],
    }


def _empty_validation_result(reason: str) -> ValidationResult:
    check: ValidationCheckResult = {
        'name': 'validation',
        'status': 'SKIPPED',
        'command': '',
        'returncode': None,
        'stdout': '',
        'stderr': '',
        'reason': reason,
    }
    return {
        'status': 'SKIPPED',
        'checks': [check],
        'summary': reason,
    }


def _run_validation(task: Mapping[str, Any], worktree_dir: Path) -> ValidationResult:
    raw_steps = task.get('validation') or []
    if not raw_steps:
        reason = _default_validation_reason(task)
        return _empty_validation_result(reason)

    if not isinstance(raw_steps, list):
        raise AdapterError(OPENCODE_EXEC_FAILED, 'task.validation must be a list', {'field': 'validation'})

    checks: List[ValidationCheckResult] = []
    passed = 0
    failed = 0
    skipped = 0

    for index, item in enumerate(raw_steps, start=1):
        name = f'validation_{index}'
        command = ''
        timeout_s = DEFAULT_VALIDATION_TIMEOUT_SECONDS

        if isinstance(item, str):
            command = item.strip()
        elif isinstance(item, Mapping):
            name = str(item.get('name') or item.get('id') or name).strip() or name
            command = str(item.get('command') or '').strip()
            raw_timeout = item.get('timeout_s')
            if raw_timeout is not None:
                try:
                    timeout_s = int(raw_timeout)
                except (TypeError, ValueError):
                    raise AdapterError(
                        OPENCODE_EXEC_FAILED,
                        'validation timeout_s must be an integer',
                        {'validation_step': name, 'timeout_s': raw_timeout},
                    )
        else:
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'each validation step must be a string or object',
                {'validation_step': index, 'actual_type': type(item).__name__},
            )

        if not command:
            skipped += 1
            checks.append(
                {
                    'name': name,
                    'status': 'SKIPPED',
                    'command': '',
                    'returncode': None,
                    'stdout': '',
                    'stderr': '',
                    'reason': 'Validation step did not define a command.',
                }
            )
            continue

        try:
            result = subprocess.run(
                ['sh', '-lc', command],
                cwd=str(worktree_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            status = 'PASSED' if result.returncode == 0 else 'FAILED'
            if status == 'PASSED':
                passed += 1
            else:
                failed += 1
            checks.append(
                {
                    'name': name,
                    'status': status,
                    'command': command,
                    'returncode': result.returncode,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'reason': '',
                }
            )
        except subprocess.TimeoutExpired as exc:
            failed += 1
            checks.append(
                {
                    'name': name,
                    'status': 'FAILED',
                    'command': command,
                    'returncode': None,
                    'stdout': _to_text(exc.stdout),
                    'stderr': _to_text(exc.stderr),
                    'reason': f'Validation command timed out after {timeout_s}s.',
                }
            )

    if failed:
        summary = f'{passed} validation step(s) passed, {failed} failed, {skipped} skipped.'
        return {'status': 'FAILED', 'checks': checks, 'summary': summary}
    if passed:
        summary = f'{passed} validation step(s) passed, {skipped} skipped.'
        return {'status': 'PASSED', 'checks': checks, 'summary': summary}
    summary = f'All {skipped} validation step(s) were skipped.'
    return {'status': 'SKIPPED', 'checks': checks, 'summary': summary}


def _default_validation_reason(task: Mapping[str, Any]) -> str:
    parts: List[str] = ['No executable validation commands were provided']
    trigger_metric = str(task.get('trigger_metric') or '').strip()
    trigger_cases = [str(item).strip() for item in task.get('trigger_cases') or [] if str(item).strip()]
    suffix: List[str] = []
    if trigger_metric:
        suffix.append(f'metric {trigger_metric}')
    if trigger_cases:
        suffix.append(f'cases {", ".join(trigger_cases)}')
    if suffix:
        parts.append(f'for {", ".join(suffix)}')
    return ''.join([parts[0], f' {parts[1]}.' if len(parts) > 1 else '.'])


def _apply_patch_to_worktree(worktree_dir: Path, patch_path: Path) -> None:
    result = _run_command(
        ['git', '-C', str(worktree_dir), 'apply', '--index', '--binary', str(patch_path)],
        timeout=60,
    )
    if result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to apply generated patch to the accepted worktree',
            {'stdout': result.stdout, 'stderr': result.stderr, 'patch_path': str(patch_path)},
        )


def _recreate_staging_worktree(repo_root: Path, worktree_dir: Path, base_commit: str) -> None:
    if worktree_dir.exists():
        remove_result = _run_command(
            ['git', '-C', str(repo_root), 'worktree', 'remove', '--force', str(worktree_dir)],
            timeout=60,
        )
        if remove_result.returncode != 0:
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'failed to remove rejected staging worktree',
                {'stdout': remove_result.stdout, 'stderr': remove_result.stderr},
            )
        prune_result = _run_command(['git', '-C', str(repo_root), 'worktree', 'prune'], timeout=30)
        if prune_result.returncode != 0:
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'failed to prune rejected staging worktree metadata',
                {'stdout': prune_result.stdout, 'stderr': prune_result.stderr},
            )
    _create_worktree(repo_root, base_commit, worktree_dir)


def _commit_worktree(worktree_dir: Path, task_id: str) -> str:
    status_result = _run_command(['git', '-C', str(worktree_dir), 'status', '--porcelain'], timeout=30)
    if status_result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to inspect accepted worktree state',
            {'stdout': status_result.stdout, 'stderr': status_result.stderr},
        )
    if not status_result.stdout.strip():
        head_result = _run_command(['git', '-C', str(worktree_dir), 'rev-parse', 'HEAD'], timeout=30)
        if head_result.returncode != 0:
            raise AdapterError(
                OPENCODE_EXEC_FAILED,
                'failed to resolve accepted worktree HEAD',
                {'stdout': head_result.stdout, 'stderr': head_result.stderr},
            )
        return head_result.stdout.strip()

    env = os.environ.copy()
    env.setdefault('GIT_AUTHOR_NAME', 'LazyRAG Automation')
    env.setdefault('GIT_AUTHOR_EMAIL', 'automation@lazyrag.local')
    env.setdefault('GIT_COMMITTER_NAME', env['GIT_AUTHOR_NAME'])
    env.setdefault('GIT_COMMITTER_EMAIL', env['GIT_AUTHOR_EMAIL'])
    commit_result = subprocess.run(
        ['git', '-C', str(worktree_dir), 'commit', '--no-verify', '-m', f'automation: {task_id}'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )
    if commit_result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to commit accepted task changes',
            {'stdout': commit_result.stdout, 'stderr': commit_result.stderr, 'task_id': task_id},
        )
    head_result = _run_command(['git', '-C', str(worktree_dir), 'rev-parse', 'HEAD'], timeout=30)
    if head_result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to resolve accepted task commit',
            {'stdout': head_result.stdout, 'stderr': head_result.stderr},
        )
    return head_result.stdout.strip()


def _collect_cumulative_diff(worktree_dir: Path, base_commit: str, current_commit: str) -> str:
    if current_commit == base_commit:
        return ''
    result = _run_command(
        ['git', '-C', str(worktree_dir), 'diff', '--binary', f'{base_commit}..{current_commit}', '--'],
        timeout=30,
        text=False,
    )
    if result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to collect cumulative report diff',
            {
                'stdout': result.stdout.decode('utf-8', errors='replace'),
                'stderr': result.stderr.decode('utf-8', errors='replace'),
            },
        )
    return result.stdout.decode('utf-8', errors='replace')


def _summarize_remaining_risks(
    *,
    task: Mapping[str, Any],
    modify_result: AdapterOutcome,
    validation_result: ValidationResult,
    extra_risk: str,
) -> List[str]:
    risks: List[str] = []
    if modify_result['status'] == 'FAILED':
        error = modify_result.get('error') or {}
        code = str(error.get('code') or 'UNKNOWN')
        message = str(error.get('message') or 'unknown modification failure')
        risks.append(f'Code modification failed ({code}): {message}.')
    elif modify_result['status'] == NO_CHANGE:
        risks.append('No code changes were applied; the reported issue may still require manual confirmation.')

    if validation_result['status'] == 'FAILED':
        failed_checks = [check['name'] for check in validation_result['checks'] if check['status'] == 'FAILED']
        if failed_checks:
            risks.append(f'Validation failed for: {", ".join(failed_checks)}.')
        else:
            risks.append('Validation failed.')
    elif validation_result['status'] == 'SKIPPED':
        risks.append(validation_result['summary'])

    if extra_risk:
        risks.append(extra_risk)

    trigger_metric = str(task.get('trigger_metric') or '').strip()
    if trigger_metric and validation_result['status'] != 'PASSED':
        risks.append(f'Improvement for trigger metric {trigger_metric} remains unverified.')

    return _dedupe_strings(risks)


def _build_report_summary(task_results: Sequence[TaskExecutionResult]) -> ReportSummary:
    files_changed: List[str] = []
    seen_files: Set[str] = set()
    remaining_risks: List[str] = []
    succeeded = 0
    partial = 0
    failed = 0
    blocked = 0
    no_change = 0

    for task_result in task_results:
        status = task_result['status']
        if status == 'SUCCEEDED':
            succeeded += 1
        elif status == 'PARTIAL':
            partial += 1
        elif status == 'FAILED':
            failed += 1
        elif status == 'BLOCKED':
            blocked += 1
        elif status == NO_CHANGE:
            no_change += 1

        modify_result = task_result.get('modify_result')
        if modify_result and modify_result.get('result'):
            for file_path in modify_result['result']['files_changed']:
                if file_path not in seen_files:
                    seen_files.add(file_path)
                    files_changed.append(file_path)

        for risk in task_result['remaining_risks']:
            if risk not in remaining_risks:
                remaining_risks.append(risk)

    return {
        'total_tasks': len(task_results),
        'succeeded': succeeded,
        'partial': partial,
        'failed': failed,
        'blocked': blocked,
        'no_change': no_change,
        'files_changed': files_changed,
        'remaining_risks': remaining_risks,
    }


def _overall_status(task_results: Sequence[TaskExecutionResult]) -> str:
    if not task_results:
        return 'FAILED'
    statuses = {task_result['status'] for task_result in task_results}
    if statuses.issubset({'SUCCEEDED', NO_CHANGE}):
        return 'SUCCEEDED'
    if statuses.issubset({'FAILED', 'BLOCKED'}):
        return 'FAILED'
    return 'PARTIAL'


def _sanitize_identifier(value: str, *, fallback: str) -> str:
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', value)
    sanitized = sanitized.strip('_')
    return sanitized or fallback


def _to_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _dedupe_strings(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    deduped: List[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _persist_report_outcome(artifacts_dir: Path, outcome: ReportOutcome) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifacts_dir / 'result.json', outcome)
