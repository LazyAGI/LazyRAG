from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from automation.opencode_adapter.errors import (
    AdapterError,
    BASE_REF_INVALID,
    GIT_REPO_INVALID,
    OPENCODE_AUTH_MISSING,
    OPENCODE_BINARY_MISSING,
    OPENCODE_EXEC_FAILED,
)
from automation.opencode_adapter.events import extract_error_event, extract_text, parse_event_stream


TASK_SCOPE_EMPTY = 'TASK_SCOPE_EMPTY'
TASK_SCOPE_FORBIDDEN = 'TASK_SCOPE_FORBIDDEN'
VALIDATION_MISSING = 'VALIDATION_MISSING'
MAX_ROUNDS_EXCEEDED = 'MAX_ROUNDS_EXCEEDED'
DEPENDENCY_BLOCKED = 'DEPENDENCY_BLOCKED'
CONSTRAINTS_PARSE_FAILED = 'CONSTRAINTS_PARSE_FAILED'
REPORT_JSON_INVALID = 'REPORT_JSON_INVALID'
SCOPE_VIOLATION = 'SCOPE_VIOLATION'
NO_CHANGE = 'NO_CHANGE'

DEFAULT_BASE_REF = 'HEAD'
DEFAULT_MAX_ROUNDS = 3
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_ARTIFACT_ROOT = Path(tempfile.gettempdir()) / 'lazy-rag-edit'
DEFAULT_CLI_INSTRUCTION = '完成这个json内的任务'
SUCCESSFUL_TASK_STATUSES = {'SUCCEEDED', NO_CHANGE}


def execute_simple_report(
    payload: Mapping[str, Any],
    *,
    repo_path: str,
    instruction: str,
    base_ref: str = DEFAULT_BASE_REF,
    opencode_options: Mapping[str, Any] | None = None,
    fallback_validation_commands: Sequence[str] | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    artifact_root: str | None = None,
) -> Dict[str, Any]:
    report_id = 'report'
    artifacts_dir = ''
    try:
        report = _extract_report(payload)
        report_id = str(report.get('report_id') or 'report').strip() or 'report'
        safe_report_id = _sanitize_identifier(report_id, fallback='report')

        artifact_base = Path(artifact_root).expanduser() if artifact_root else DEFAULT_ARTIFACT_ROOT
        artifact_base.mkdir(parents=True, exist_ok=True)
        run_root = Path(
            tempfile.mkdtemp(prefix=f'{safe_report_id}_', dir=str(artifact_base.resolve()))
        ).resolve()
        artifacts_dir = str(run_root)

        _write_json(run_root / 'input.report.json', report)

        repo_root = _validate_repo(repo_path)
        normalized_base_ref = _resolve_base_ref(repo_root, base_ref)
        hard_allowlist = _load_hard_allowlist()

        merged_opencode = _merge_opencode_options(
            _coerce_mapping(report.get('opencode'), 'opencode', allow_none=True),
            opencode_options or {},
        )
        binary = _resolve_opencode_binary(merged_opencode)
        _preflight_opencode(binary)

        accepted_repo = run_root / 'accepted_repo'
        _materialize_base_copy(repo_root, normalized_base_ref, accepted_repo)

        task_results: List[Dict[str, Any]] = []
        task_statuses: Dict[str, str] = {}
        fallback_commands = [command for command in (fallback_validation_commands or []) if command.strip()]

        for task in _extract_tasks(report):
            task_result = _execute_task(
                task=task,
                report=report,
                instruction=instruction,
                accepted_repo=accepted_repo,
                run_root=run_root,
                hard_allowlist=hard_allowlist,
                binary=binary,
                opencode_options=merged_opencode,
                fallback_validation_commands=fallback_commands,
                max_rounds=max_rounds,
                task_statuses=task_statuses,
            )
            task_results.append(task_result)
            task_statuses[task_result['task_id']] = task_result['status']

        outcome = {
            'status': _overall_status(task_results),
            'report_id': report_id,
            'task_results': task_results,
            'summary': _build_summary(task_results),
            'error': None,
            'artifacts_dir': artifacts_dir,
        }
        _write_json(run_root / 'result.json', outcome)
        return outcome
    except AdapterError as exc:
        outcome = {
            'status': 'FAILED',
            'report_id': report_id,
            'task_results': [],
            'summary': _build_summary([]),
            'error': exc.to_payload(),
            'artifacts_dir': artifacts_dir,
        }
        if artifacts_dir:
            _write_json(Path(artifacts_dir) / 'result.json', outcome)
        return outcome
    except Exception as exc:
        wrapped = AdapterError(OPENCODE_EXEC_FAILED, 'unexpected simple runner failure', {'error': str(exc)})
        outcome = {
            'status': 'FAILED',
            'report_id': report_id,
            'task_results': [],
            'summary': _build_summary([]),
            'error': wrapped.to_payload(),
            'artifacts_dir': artifacts_dir,
        }
        if artifacts_dir:
            _write_json(Path(artifacts_dir) / 'result.json', outcome)
        return outcome


def _execute_task(
    *,
    task: MutableMapping[str, Any],
    report: MutableMapping[str, Any],
    instruction: str,
    accepted_repo: Path,
    run_root: Path,
    hard_allowlist: Sequence[str],
    binary: str,
    opencode_options: Mapping[str, Any],
    fallback_validation_commands: Sequence[str],
    max_rounds: int,
    task_statuses: Mapping[str, str],
) -> Dict[str, Any]:
    task_id = str(task.get('task_id') or 'task').strip() or 'task'
    module = str(task.get('module') or '').strip()
    safe_task_id = _sanitize_identifier(task_id, fallback='task')
    task_root = run_root / 'tasks' / safe_task_id
    task_root.mkdir(parents=True, exist_ok=True)
    _write_json(task_root / 'task.json', task)

    dependency_error = _dependency_error(task, task_statuses)
    if dependency_error is not None:
        validation = _skipped_validation(dependency_error.message)
        result = _task_result(
            task_id=task_id,
            module=module,
            status='BLOCKED',
            rounds=0,
            allowed_files=[],
            task_root=task_root,
            result=None,
            error=dependency_error.to_payload(),
            validation_result=validation,
        )
        _write_json(task_root / 'result.json', result)
        return result

    try:
        allowed_files = _resolve_task_scope(task, hard_allowlist)
        validation_commands = _validation_commands_for_task(task, fallback_validation_commands)
    except AdapterError as exc:
        validation = _skipped_validation(exc.message)
        result = _task_result(
            task_id=task_id,
            module=module,
            status='FAILED',
            rounds=0,
            allowed_files=[],
            task_root=task_root,
            result=None,
            error=exc.to_payload(),
            validation_result=validation,
        )
        _write_json(task_root / 'result.json', result)
        return result

    feedback = ''
    last_validation = _skipped_validation('Validation was not run.')
    round_source = accepted_repo

    for round_index in range(1, max_rounds + 1):
        round_root = task_root / f'round_{round_index}'
        round_repo = round_root / 'repo'
        round_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(round_source, round_repo)

        prompt = _build_prompt(
            instruction=instruction,
            report=report,
            task=task,
            allowed_files=allowed_files,
            feedback=feedback,
        )
        _write_text(round_root / 'prompt.txt', prompt)

        try:
            events, stderr = _run_opencode(
                binary=binary,
                repo_copy=round_repo,
                prompt=prompt,
                options=opencode_options,
            )
        except AdapterError as exc:
            validation = _skipped_validation('Validation skipped because OpenCode execution failed.')
            result = _task_result(
                task_id=task_id,
                module=module,
                status='FAILED',
                rounds=round_index,
                allowed_files=allowed_files,
                task_root=task_root,
                result=None,
                error=exc.to_payload(),
                validation_result=validation,
            )
            _write_json(task_root / 'result.json', result)
            return result

        _write_jsonl(round_root / 'events.jsonl', events)
        _write_text(round_root / 'stderr.log', stderr)

        changed_files = _collect_changed_files(round_repo)
        violations = sorted(path for path in changed_files if path not in set(allowed_files))
        if violations:
            error = AdapterError(
                SCOPE_VIOLATION,
                'OpenCode modified files outside the allowed scope',
                {'violations': violations, 'allowed_files': allowed_files},
            )
            validation = _skipped_validation('Validation skipped because scope verification failed.')
            result = _task_result(
                task_id=task_id,
                module=module,
                status='FAILED',
                rounds=round_index,
                allowed_files=allowed_files,
                task_root=task_root,
                result=None,
                error=error.to_payload(),
                validation_result=validation,
            )
            _write_json(task_root / 'result.json', result)
            return result

        diff_text = _collect_diff(round_repo) if changed_files else ''
        change_summary = extract_text(events) or _build_change_summary(changed_files, diff_text)
        modify_result = {
            'diff': diff_text,
            'files_changed': changed_files,
            'change_summary': change_summary or 'No changes were necessary.',
        }

        validation = _run_validation_commands(round_repo, validation_commands)
        _write_json(round_root / 'validation.json', validation)
        last_validation = validation

        if validation['status'] == 'PASSED':
            if changed_files:
                _commit_changes(round_repo, task_id)
                _promote_accepted_repo(round_repo, accepted_repo)
                status = 'SUCCEEDED'
            else:
                status = NO_CHANGE

            result = _task_result(
                task_id=task_id,
                module=module,
                status=status,
                rounds=round_index,
                allowed_files=allowed_files,
                task_root=task_root,
                result=modify_result,
                error=None,
                validation_result=validation,
            )
            _write_json(task_root / 'result.json', result)
            return result

        feedback = _validation_feedback(validation)
        round_source = round_repo

    error = AdapterError(
        MAX_ROUNDS_EXCEEDED,
        'validation did not pass within max_rounds',
        {'max_rounds': max_rounds, 'last_validation': last_validation},
    )
    result = _task_result(
        task_id=task_id,
        module=module,
        status='FAILED',
        rounds=max_rounds,
        allowed_files=allowed_files,
        task_root=task_root,
        result=None,
        error=error.to_payload(),
        validation_result=last_validation,
    )
    _write_json(task_root / 'result.json', result)
    return result


def _task_result(
    *,
    task_id: str,
    module: str,
    status: str,
    rounds: int,
    allowed_files: Sequence[str],
    task_root: Path,
    result: Optional[Dict[str, Any]],
    error: Optional[Dict[str, Any]],
    validation_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        'task_id': task_id,
        'module': module,
        'status': status,
        'rounds': rounds,
        'allowed_files': list(allowed_files),
        'result': result,
        'error': error,
        'validation_result': validation_result,
        'artifacts_dir': str(task_root),
    }


def _extract_report(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    report = _coerce_mapping(payload.get('report') if 'report' in payload else payload, 'report')
    task_plans = report.get('task_plans')
    if not isinstance(task_plans, list):
        raise AdapterError(REPORT_JSON_INVALID, 'report.task_plans must be a list', {'field': 'task_plans'})
    return report


def _extract_tasks(report: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    tasks: List[MutableMapping[str, Any]] = []
    for index, item in enumerate(report.get('task_plans') or []):
        if not isinstance(item, MutableMapping):
            raise AdapterError(
                REPORT_JSON_INVALID,
                'each task_plan must be an object',
                {'field': f'task_plans[{index}]', 'actual_type': type(item).__name__},
            )
        tasks.append(item)
    return tasks


def _dependency_error(task: Mapping[str, Any], task_statuses: Mapping[str, str]) -> AdapterError | None:
    dependencies = task.get('depends_on') or []
    if dependencies and not isinstance(dependencies, list):
        return AdapterError(
            REPORT_JSON_INVALID,
            'depends_on must be a list',
            {'task_id': str(task.get('task_id') or ''), 'field': 'depends_on'},
        )
    for dependency in dependencies:
        dependency_id = str(dependency).strip()
        if task_statuses.get(dependency_id) not in SUCCESSFUL_TASK_STATUSES:
            return AdapterError(
                DEPENDENCY_BLOCKED,
                f'task dependency {dependency_id} did not complete successfully',
                {'depends_on': dependency_id},
            )
    return None


def _resolve_task_scope(task: Mapping[str, Any], hard_allowlist: Sequence[str]) -> List[str]:
    raw_targets = task.get('change_targets') or []
    if not isinstance(raw_targets, list):
        raise AdapterError(
            REPORT_JSON_INVALID,
            'task.change_targets must be a list',
            {'task_id': str(task.get('task_id') or ''), 'field': 'change_targets'},
        )

    allowed_set = set(hard_allowlist)
    requested: List[str] = []
    seen: set[str] = set()
    forbidden: List[str] = []
    for index, item in enumerate(raw_targets):
        if not isinstance(item, Mapping):
            raise AdapterError(
                REPORT_JSON_INVALID,
                'each change_target must be an object',
                {'field': f'change_targets[{index}]', 'actual_type': type(item).__name__},
            )
        raw_file = str(item.get('file') or '').strip()
        if not raw_file:
            continue
        normalized = _normalize_relative_path(raw_file)
        if normalized in seen:
            continue
        seen.add(normalized)
        requested.append(normalized)
        if normalized not in allowed_set:
            forbidden.append(normalized)

    if forbidden:
        raise AdapterError(
            TASK_SCOPE_FORBIDDEN,
            'task requested files outside the hard allowlist',
            {'forbidden_files': forbidden},
        )
    if not requested:
        raise AdapterError(TASK_SCOPE_EMPTY, 'task has no allowed change_targets', {})
    return requested


def _validation_commands_for_task(task: Mapping[str, Any], fallback_commands: Sequence[str]) -> List[Dict[str, Any]]:
    raw_steps = task.get('validation')
    if raw_steps is None:
        raw_steps = list(fallback_commands)

    if not raw_steps:
        raise AdapterError(
            VALIDATION_MISSING,
            'no validation commands were provided for this task',
            {'task_id': str(task.get('task_id') or '')},
        )
    if not isinstance(raw_steps, list):
        raise AdapterError(
            REPORT_JSON_INVALID,
            'task.validation must be a list',
            {'task_id': str(task.get('task_id') or ''), 'field': 'validation'},
        )

    commands: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_steps, start=1):
        if isinstance(item, str):
            command = item.strip()
            if command:
                commands.append({'name': f'validation_{index}', 'command': command, 'timeout_s': DEFAULT_TIMEOUT_SECONDS})
            continue
        if isinstance(item, Mapping):
            command = str(item.get('command') or '').strip()
            if not command:
                continue
            timeout_value = item.get('timeout_s')
            timeout_s = DEFAULT_TIMEOUT_SECONDS
            if timeout_value is not None:
                try:
                    timeout_s = int(timeout_value)
                except (TypeError, ValueError) as exc:
                    raise AdapterError(
                        REPORT_JSON_INVALID,
                        'validation timeout_s must be an integer',
                        {'task_id': str(task.get('task_id') or ''), 'validation_step': index},
                    ) from exc
            commands.append(
                {
                    'name': str(item.get('name') or item.get('id') or f'validation_{index}').strip() or f'validation_{index}',
                    'command': command,
                    'timeout_s': timeout_s,
                }
            )
            continue
        raise AdapterError(
            REPORT_JSON_INVALID,
            'each validation step must be a string or object',
            {'task_id': str(task.get('task_id') or ''), 'validation_step': index},
        )

    if not commands:
        raise AdapterError(
            VALIDATION_MISSING,
            'no executable validation commands were provided for this task',
            {'task_id': str(task.get('task_id') or '')},
        )
    return commands


def _build_prompt(
    *,
    instruction: str,
    report: Mapping[str, Any],
    task: Mapping[str, Any],
    allowed_files: Sequence[str],
    feedback: str,
) -> str:
    report_context = {
        'report_id': report.get('report_id'),
        'top_issue': report.get('top_issue'),
        'instruction': report.get('instruction'),
        'constraints': report.get('constraints'),
        'case': report.get('case'),
    }
    scope_lines = '\n'.join(f'- {path}' for path in allowed_files)
    feedback_block = feedback.strip() if feedback.strip() else 'None.'
    return textwrap.dedent(
        f"""
        You are editing a copied repository, not the original repository.

        User instruction:
        {instruction}

        Hard constraints:
        - Only modify files in this allowlist:
        {scope_lines}
        - Do not modify any other file, even if the task plan mentions it.
        - Keep changes minimal and directly tied to the current task.
        - End with a concise plain-text change summary in 1-3 sentences.
        - The host will reject any out-of-scope file modification.

        Report context:
        {json.dumps(report_context, ensure_ascii=False, indent=2, sort_keys=True)}

        Current task:
        {json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True)}

        Previous validation feedback:
        {feedback_block}
        """
    ).strip()


def _validate_repo(repo_path: str) -> Path:
    if not repo_path:
        raise AdapterError(GIT_REPO_INVALID, 'repo path is required', {'field': 'repo_path'})
    repo_root = Path(repo_path).expanduser().resolve()
    if not repo_root.is_dir():
        raise AdapterError(GIT_REPO_INVALID, 'repo path does not exist', {'repo_path': repo_path})
    result = _run_command(['git', '-C', str(repo_root), 'rev-parse', '--is-inside-work-tree'], timeout=30)
    if result.returncode != 0 or result.stdout.strip() != 'true':
        raise AdapterError(
            GIT_REPO_INVALID,
            'repo path is not a git repository',
            {'repo_path': str(repo_root), 'stderr': result.stderr.strip()},
        )
    return repo_root


def _resolve_base_ref(repo_root: Path, base_ref: str) -> str:
    normalized = base_ref.strip() or DEFAULT_BASE_REF
    result = _run_command(
        ['git', '-C', str(repo_root), 'rev-parse', '--verify', f'{normalized}^{{commit}}'],
        timeout=30,
    )
    if result.returncode != 0:
        raise AdapterError(
            BASE_REF_INVALID,
            'base_ref could not be resolved to a commit',
            {'base_ref': normalized, 'stderr': result.stderr.strip()},
        )
    return normalized


ALLOWED_FILE_SCOPE = [
    'algorithm/chat/prompts/rewrite.py',
    'algorithm/chat/prompts/agentic.py',
    'algorithm/chat/prompts/rag_answer.py',
    'algorithm/chat/components/process/multiturn_query_rewriter.py',
    'algorithm/chat/components/process/sensitive_filter.py',
    'algorithm/chat/components/process/context_expansion.py',
    'algorithm/chat/components/process/adaptive_topk.py',
    'algorithm/chat/components/generate/output_parser.py',
    'algorithm/chat/components/generate/prompt_formatter.py',
    'algorithm/chat/components/generate/aggregate.py',
    'algorithm/chat/components/tmp/local_models.py',
    'algorithm/chat/components/tmp/tool_registry.py',
    'algorithm/chat/pipelines/builders/get_retriever.py',
    'algorithm/chat/pipelines/builders/get_ppl_search.py',
    'algorithm/chat/pipelines/builders/get_ppl_generate.py',
    'algorithm/chat/pipelines/naive.py',
]


def _load_hard_allowlist() -> List[str]:
    return list(ALLOWED_FILE_SCOPE)


def _merge_opencode_options(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def _resolve_opencode_binary(options: Mapping[str, Any]) -> str:
    configured = str(options.get('binary') or os.getenv('OPENCODE_BIN') or '').strip()
    binary = configured or shutil.which('opencode') or ''
    if not binary:
        raise AdapterError(OPENCODE_BINARY_MISSING, 'opencode binary was not found on PATH', {})
    return binary


def _preflight_opencode(binary: str) -> None:
    result = _run_command([binary, 'auth', 'list'], timeout=30)
    combined = '\n'.join(part for part in [result.stdout, result.stderr] if part)
    if result.returncode != 0:
        raise AdapterError(
            OPENCODE_AUTH_MISSING,
            'opencode auth list failed',
            {'stdout': result.stdout, 'stderr': result.stderr},
        )
    match = re.search(r'(\d+)\s+credentials', combined)
    credential_count = int(match.group(1)) if match else 0
    if credential_count < 1:
        raise AdapterError(OPENCODE_AUTH_MISSING, 'opencode has no configured credentials', {'output': combined})


def _materialize_base_copy(repo_root: Path, base_ref: str, target_dir: Path) -> None:
    archive_result = _run_command(
        ['git', '-C', str(repo_root), 'archive', '--format=tar', base_ref],
        timeout=60,
        text=False,
    )
    if archive_result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to archive repository at base_ref',
            {
                'base_ref': base_ref,
                'stdout': archive_result.stdout.decode('utf-8', errors='replace'),
                'stderr': archive_result.stderr.decode('utf-8', errors='replace'),
            },
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive_result.stdout), mode='r:') as handle:
        for member in handle.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or '..' in member_path.parts:
                raise AdapterError(
                    CONSTRAINTS_PARSE_FAILED,
                    'git archive produced an unsafe member path',
                    {'member': member.name},
                )
        handle.extractall(path=target_dir)

    _run_command(['git', '-C', str(target_dir), 'init'], timeout=30, required=True)
    _run_command(['git', '-C', str(target_dir), 'config', 'user.email', 'automation@example.com'], timeout=30, required=True)
    _run_command(['git', '-C', str(target_dir), 'config', 'user.name', 'LazyRAG Automation'], timeout=30, required=True)
    _run_command(['git', '-C', str(target_dir), 'add', '-A', '--', '.'], timeout=30, required=True)
    _run_command(['git', '-C', str(target_dir), 'commit', '-m', 'baseline'], timeout=30, required=True)


def _run_opencode(
    *,
    binary: str,
    repo_copy: Path,
    prompt: str,
    options: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], str]:
    command = [binary, 'run', '--format', 'json']
    for flag in ('model', 'agent', 'variant'):
        value = str(options.get(flag) or '').strip()
        if value:
            command.extend([f'--{flag}', value])
    command.append(prompt)
    timeout = int(options.get('timeout_s') or DEFAULT_TIMEOUT_SECONDS)
    result = _run_command(command, cwd=repo_copy, timeout=timeout)
    events = parse_event_stream(result.stdout)
    if result.returncode != 0:
        details: Dict[str, Any] = {'returncode': result.returncode, 'stderr': result.stderr}
        error_event = extract_error_event(events)
        if error_event is not None:
            details['event'] = error_event
        raise AdapterError(OPENCODE_EXEC_FAILED, 'opencode run failed', details)
    return events, result.stderr


def _collect_changed_files(repo_copy: Path) -> List[str]:
    tracked = _split_null_terminated(
        _run_command(['git', '-C', str(repo_copy), 'diff', '--name-only', '-z', 'HEAD', '--'], timeout=30).stdout
    )
    untracked = _split_null_terminated(
        _run_command(
            ['git', '-C', str(repo_copy), 'ls-files', '--others', '--exclude-standard', '-z'],
            timeout=30,
        ).stdout
    )
    return sorted(set(tracked) | set(untracked))


def _collect_diff(repo_copy: Path) -> str:
    _run_command(['git', '-C', str(repo_copy), 'add', '-A', '--', '.'], timeout=30, required=True)
    result = _run_command(
        ['git', '-C', str(repo_copy), 'diff', '--cached', '--binary', 'HEAD', '--'],
        timeout=30,
        text=False,
    )
    if result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to collect git diff from copied repository',
            {
                'stdout': result.stdout.decode('utf-8', errors='replace'),
                'stderr': result.stderr.decode('utf-8', errors='replace'),
            },
        )
    return result.stdout.decode('utf-8', errors='replace')


def _commit_changes(repo_copy: Path, task_id: str) -> None:
    status = _run_command(['git', '-C', str(repo_copy), 'status', '--porcelain'], timeout=30)
    if status.returncode != 0:
        raise AdapterError(OPENCODE_EXEC_FAILED, 'failed to inspect copied repo status', {'stderr': status.stderr})
    if not status.stdout.strip():
        return
    _run_command(['git', '-C', str(repo_copy), 'add', '-A', '--', '.'], timeout=30, required=True)
    _run_command(['git', '-C', str(repo_copy), 'commit', '-m', f'automation: {task_id}'], timeout=30, required=True)


def _promote_accepted_repo(source_repo: Path, accepted_repo: Path) -> None:
    temp_dir = accepted_repo.parent / f'{accepted_repo.name}.next'
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    shutil.copytree(source_repo, temp_dir)
    shutil.rmtree(accepted_repo, ignore_errors=True)
    temp_dir.replace(accepted_repo)


def _run_validation_commands(repo_copy: Path, commands: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    failures = 0
    for command_info in commands:
        command = str(command_info['command']).strip()
        timeout_s = int(command_info.get('timeout_s') or DEFAULT_TIMEOUT_SECONDS)
        try:
            result = subprocess.run(
                ['sh', '-lc', command],
                cwd=str(repo_copy),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            status = 'PASSED' if result.returncode == 0 else 'FAILED'
            if status == 'FAILED':
                failures += 1
            checks.append(
                {
                    'name': str(command_info.get('name') or 'validation').strip() or 'validation',
                    'status': status,
                    'command': command,
                    'returncode': result.returncode,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'reason': '',
                }
            )
        except subprocess.TimeoutExpired as exc:
            failures += 1
            checks.append(
                {
                    'name': str(command_info.get('name') or 'validation').strip() or 'validation',
                    'status': 'FAILED',
                    'command': command,
                    'returncode': None,
                    'stdout': _to_text(exc.stdout),
                    'stderr': _to_text(exc.stderr),
                    'reason': f'Validation command timed out after {timeout_s}s.',
                }
            )

    if failures:
        summary = f'{len(commands) - failures} validation step(s) passed, {failures} failed.'
        return {'status': 'FAILED', 'checks': checks, 'summary': summary}
    summary = f'{len(commands)} validation step(s) passed.'
    return {'status': 'PASSED', 'checks': checks, 'summary': summary}


def _to_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _skipped_validation(reason: str) -> Dict[str, Any]:
    return {
        'status': 'SKIPPED',
        'checks': [
            {
                'name': 'validation',
                'status': 'SKIPPED',
                'command': '',
                'returncode': None,
                'stdout': '',
                'stderr': '',
                'reason': reason,
            }
        ],
        'summary': reason,
    }


def _validation_feedback(validation: Mapping[str, Any]) -> str:
    lines = [str(validation.get('summary') or '').strip()]
    for check in validation.get('checks') or []:
        if check.get('status') != 'FAILED':
            continue
        lines.append(f"[{check.get('name')}] command: {check.get('command')}")
        stdout = str(check.get('stdout') or '').strip()
        stderr = str(check.get('stderr') or '').strip()
        reason = str(check.get('reason') or '').strip()
        if stdout:
            lines.append(f'stdout:\n{stdout}')
        if stderr:
            lines.append(f'stderr:\n{stderr}')
        if reason:
            lines.append(f'reason: {reason}')
    return '\n'.join(line for line in lines if line)


def _build_change_summary(files_changed: Sequence[str], diff_text: str) -> str:
    if not files_changed:
        return 'No changes were necessary.'
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith('+++') or line.startswith('---'):
            continue
        if line.startswith('+'):
            additions += 1
        elif line.startswith('-'):
            deletions += 1
    listed = ', '.join(files_changed[:3])
    if len(files_changed) > 3:
        listed = f'{listed}, ...'
    noun = 'file' if len(files_changed) == 1 else 'files'
    return f'Updated {len(files_changed)} {noun} ({listed}); +{additions}/-{deletions} changed lines.'


def _overall_status(task_results: Sequence[Mapping[str, Any]]) -> str:
    if not task_results:
        return 'FAILED'
    statuses = {str(item.get('status') or '') for item in task_results}
    if statuses.issubset({'SUCCEEDED', NO_CHANGE}):
        return 'SUCCEEDED'
    if statuses.issubset({'FAILED', 'BLOCKED'}):
        return 'FAILED'
    return 'PARTIAL'


def _build_summary(task_results: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    summary = {'total_tasks': len(task_results), 'succeeded': 0, 'failed': 0, 'blocked': 0, 'no_change': 0}
    for item in task_results:
        status = str(item.get('status') or '')
        if status == 'SUCCEEDED':
            summary['succeeded'] += 1
        elif status == 'FAILED':
            summary['failed'] += 1
        elif status == 'BLOCKED':
            summary['blocked'] += 1
        elif status == NO_CHANGE:
            summary['no_change'] += 1
    return summary


def _coerce_mapping(value: Any, field_name: str, *, allow_none: bool = False) -> MutableMapping[str, Any]:
    if value is None:
        if allow_none:
            return {}
        raise AdapterError(REPORT_JSON_INVALID, f'{field_name} is required', {'field': field_name})
    if not isinstance(value, MutableMapping):
        raise AdapterError(
            REPORT_JSON_INVALID,
            f'{field_name} must be an object',
            {'field': field_name, 'actual_type': type(value).__name__},
        )
    return value


def _normalize_relative_path(path_value: str) -> str:
    candidate = Path(path_value.strip())
    if candidate.is_absolute():
        raise AdapterError(TASK_SCOPE_FORBIDDEN, 'absolute file paths are not allowed in task scope', {'path': path_value})
    normalized = candidate.as_posix().strip('/')
    if not normalized or normalized.startswith('../') or '/..' in normalized:
        raise AdapterError(TASK_SCOPE_FORBIDDEN, 'task scope path must stay inside the repository', {'path': path_value})
    return normalized


def _sanitize_identifier(value: str, *, fallback: str) -> str:
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', value).strip('_')
    return sanitized or fallback


def _split_null_terminated(output: str) -> List[str]:
    if not output:
        return []
    return [item for item in output.split('\0') if item]


def _run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int,
    text: bool = True,
    required: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AdapterError(OPENCODE_BINARY_MISSING, 'command binary was not found', {'args': list(args)}) from exc
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'command timed out',
            {'args': list(args), 'timeout_s': timeout, 'stdout': exc.stdout, 'stderr': exc.stderr},
        ) from exc

    if required and result.returncode != 0:
        stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode('utf-8', errors='replace')
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'command failed',
            {'args': list(args), 'returncode': result.returncode, 'stdout': stdout, 'stderr': stderr},
        )
    return result


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def _write_jsonl(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = ''.join(f'{json.dumps(event, ensure_ascii=False)}\n' for event in events)
    path.write_text(content, encoding='utf-8')


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _load_json(path: str) -> MutableMapping[str, Any]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise AdapterError(REPORT_JSON_INVALID, 'report json file was not found', {'path': str(candidate)})
    loaded = json.loads(candidate.read_text(encoding='utf-8'))
    return _coerce_mapping(loaded, 'report')


def _existing_file_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value).expanduser().resolve()
    if candidate.is_file():
        return candidate
    return None


def _resolve_cli_report_path(positional_input: str | None, explicit_report_json: str | None) -> Path:
    explicit_path = _existing_file_path(explicit_report_json)
    if explicit_report_json:
        if explicit_path is None:
            candidate = Path(explicit_report_json).expanduser().resolve()
            raise AdapterError(REPORT_JSON_INVALID, 'report json file was not found', {'path': str(candidate)})
        return explicit_path

    positional_path = _existing_file_path(positional_input)
    if positional_path is not None:
        return positional_path

    raise AdapterError(
        REPORT_JSON_INVALID,
        'report json path is required; pass --report-json or provide the json path as the only positional argument',
        {},
    )


def _resolve_cli_instruction(
    positional_input: str | None,
    report_json_path: Path,
    explicit_instruction: str | None,
) -> str:
    if explicit_instruction and explicit_instruction.strip():
        return explicit_instruction.strip()

    if positional_input:
        positional_path = _existing_file_path(positional_input)
        if positional_path is None or positional_path != report_json_path:
            return positional_input.strip()

    return DEFAULT_CLI_INSTRUCTION


def _discover_git_repo_root(start_path: Path) -> Path | None:
    probe = start_path if start_path.is_dir() else start_path.parent
    try:
        result = subprocess.run(
            ['git', '-C', str(probe), 'rev-parse', '--show-toplevel'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    resolved = result.stdout.strip()
    if not resolved:
        return None
    return Path(resolved).resolve()


def _resolve_cli_repo_path(
    explicit_repo: str | None,
    report: Mapping[str, Any],
    report_json_path: Path,
) -> str:
    if explicit_repo and explicit_repo.strip():
        return str(Path(explicit_repo).expanduser().resolve())

    report_repo = str(report.get('repo_path') or '').strip()
    if report_repo:
        return report_repo

    cwd_repo = _discover_git_repo_root(Path.cwd())
    if cwd_repo is not None:
        return str(cwd_repo)

    report_repo_root = _discover_git_repo_root(report_json_path.parent)
    if report_repo_root is not None:
        return str(report_repo_root)

    return ''


def _render_outcome(outcome: Mapping[str, Any], *, pretty: bool, output_path: str | None) -> int:
    rendered = json.dumps(outcome, ensure_ascii=False, indent=2 if pretty else None)
    print(rendered)
    if output_path:
        Path(output_path).write_text(rendered + '\n', encoding='utf-8')
    return 0 if outcome.get('status') == 'SUCCEEDED' else 1


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the simplified OpenCode report runner.')
    parser.add_argument(
        'input',
        nargs='?',
        help='Path to the upstream report JSON file, or a natural-language instruction when used with --report-json.',
    )
    parser.add_argument('--instruction', help='Optional natural-language instruction. Defaults to 完成这个json内的任务.')
    parser.add_argument('--report-json', help='Path to the upstream report JSON file.')
    parser.add_argument('--repo', help='Path to the repository to copy and edit.')
    parser.add_argument('--base-ref', default=DEFAULT_BASE_REF, help='Git ref to archive before copying the repo.')
    parser.add_argument('--validation-cmd', action='append', default=[], help='Fallback validation command. Repeatable.')
    parser.add_argument('--max-rounds', type=int, default=DEFAULT_MAX_ROUNDS, help='Maximum edit / validate rounds per task.')
    parser.add_argument('--binary', help='Path to the opencode binary.')
    parser.add_argument('--model', help='Optional opencode model flag.')
    parser.add_argument('--agent', help='Optional opencode agent flag.')
    parser.add_argument('--variant', help='Optional opencode variant flag.')
    parser.add_argument('--timeout-s', type=int, help='Optional opencode timeout in seconds.')
    parser.add_argument('--artifact-root', help='Optional directory for task artifacts.')
    parser.add_argument('--output', help='Write the final JSON to this file in addition to stdout.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print the JSON output.')
    args = parser.parse_args()

    try:
        report_json_path = _resolve_cli_report_path(args.input, args.report_json)
        payload = _load_json(str(report_json_path))
        report = _extract_report(payload)
        instruction = _resolve_cli_instruction(args.input, report_json_path, args.instruction)
        repo_path = _resolve_cli_repo_path(args.repo, report, report_json_path)
    except AdapterError as exc:
        outcome = {
            'status': 'FAILED',
            'report_id': 'report',
            'task_results': [],
            'summary': _build_summary([]),
            'error': exc.to_payload(),
            'artifacts_dir': '',
        }
        return _render_outcome(outcome, pretty=args.pretty, output_path=args.output)

    opencode_options = {
        'binary': args.binary,
        'model': args.model,
        'agent': args.agent,
        'variant': args.variant,
        'timeout_s': args.timeout_s,
    }
    outcome = execute_simple_report(
        report,
        repo_path=repo_path,
        instruction=instruction,
        base_ref=args.base_ref,
        opencode_options=opencode_options,
        fallback_validation_commands=args.validation_cmd,
        max_rounds=args.max_rounds,
        artifact_root=args.artifact_root,
    )
    return _render_outcome(outcome, pretty=args.pretty, output_path=args.output)


if __name__ == '__main__':
    raise SystemExit(main())
