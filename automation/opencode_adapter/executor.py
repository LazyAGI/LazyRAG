from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from automation.opencode_adapter.errors import (
    AdapterError,
    BASE_REF_INVALID,
    GIT_REPO_INVALID,
    NO_CHANGE,
    OPENCODE_AUTH_MISSING,
    OPENCODE_BINARY_MISSING,
    OPENCODE_EXEC_FAILED,
    SCOPE_VIOLATION,
    TARGET_FILE_MISSING,
)
from automation.opencode_adapter.events import extract_error_event, extract_text, parse_event_stream
from automation.opencode_adapter.prompt import build_prompt
from automation.opencode_adapter.types import AdapterOutcome, ModifyResult


DEFAULT_BASE_REF = 'HEAD'
DEFAULT_TIMEOUT_SECONDS = 300


def execute(payload: Mapping[str, Any]) -> AdapterOutcome:
    input_payload = _coerce_mapping(payload, 'payload')
    task_plan = _coerce_mapping(input_payload.get('task_plan'), 'task_plan')
    code_context = _coerce_mapping(input_payload.get('code_context'), 'code_context', allow_none=True)
    task_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(task_plan.get('task_id') or 'task'))
    repo_hint = str(input_payload.get('repo_path') or '').strip()
    artifact_base = _artifact_base(repo_hint)
    artifacts_dir = artifact_base / '.automation' / 'opencode' / task_id
    relative_artifacts_dir = _display_artifacts_dir(artifact_base, artifacts_dir)

    _cleanup_artifacts(repo_hint, artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifacts_dir / 'input.json', input_payload)

    try:
        repo_root = _validate_repo(repo_hint)
        base_ref = str(input_payload.get('base_ref') or DEFAULT_BASE_REF).strip() or DEFAULT_BASE_REF
        base_commit = _resolve_base_commit(repo_root, base_ref)
        allowlist, target_file = _resolve_allowlist(repo_root, code_context)
        binary = _resolve_opencode_binary(input_payload)
        _preflight_opencode(binary)
        worktree_dir = artifacts_dir / 'worktree'
        _create_worktree(repo_root, base_commit, worktree_dir)
        if target_file:
            _validate_target_in_worktree(worktree_dir, target_file)

        prompt = build_prompt(task_plan=task_plan, code_context=code_context, allowlist=allowlist)
        _write_text(artifacts_dir / 'prompt.txt', prompt)

        events, stderr = _run_opencode(
            binary=binary,
            worktree_dir=worktree_dir,
            prompt=prompt,
            options=_coerce_mapping(input_payload.get('opencode'), 'opencode', allow_none=True),
        )
        _write_jsonl(artifacts_dir / 'events.jsonl', events)
        _write_text(artifacts_dir / 'stderr.log', stderr)

        summary_text = extract_text(events)
        changed_files = _collect_changed_files(worktree_dir)
        if not changed_files:
            result: ModifyResult = {
                'diff': '',
                'files_changed': [],
                'change_summary': summary_text or 'No changes made by OpenCode.',
            }
            outcome: AdapterOutcome = {
                'status': NO_CHANGE,
                'result': result,
                'error': None,
                'artifacts_dir': relative_artifacts_dir,
            }
            _write_text(artifacts_dir / 'diff.patch', '')
            _write_json(artifacts_dir / 'result.json', outcome)
            return outcome

        violations = sorted(path for path in changed_files if allowlist and path not in set(allowlist))
        if violations:
            raise AdapterError(
                SCOPE_VIOLATION,
                'OpenCode modified files outside the allowlist',
                {'violations': violations, 'allowlist': allowlist},
            )

        diff_text = _stage_and_collect_diff(worktree_dir, changed_files)
        change_summary = summary_text or build_change_summary(changed_files, diff_text)
        result = {
            'diff': diff_text,
            'files_changed': changed_files,
            'change_summary': change_summary,
        }
        outcome = {
            'status': 'SUCCEEDED',
            'result': result,
            'error': None,
            'artifacts_dir': relative_artifacts_dir,
        }
        _write_text(artifacts_dir / 'diff.patch', diff_text)
        _write_json(artifacts_dir / 'result.json', outcome)
        return outcome
    except AdapterError as exc:
        outcome = {
            'status': 'FAILED',
            'result': None,
            'error': exc.to_payload(),
            'artifacts_dir': relative_artifacts_dir,
        }
        _write_json(artifacts_dir / 'result.json', outcome)
        return outcome
    except Exception as exc:
        wrapped = AdapterError(
            OPENCODE_EXEC_FAILED,
            'unexpected adapter failure',
            {'error': str(exc)},
        )
        outcome = {
            'status': 'FAILED',
            'result': None,
            'error': wrapped.to_payload(),
            'artifacts_dir': relative_artifacts_dir,
        }
        _write_json(artifacts_dir / 'result.json', outcome)
        return outcome


def build_change_summary(files_changed: Sequence[str], diff_text: str) -> str:
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith('+++') or line.startswith('---'):
            continue
        if line.startswith('+'):
            additions += 1
        elif line.startswith('-'):
            deletions += 1
    file_count = len(files_changed)
    listed = ', '.join(files_changed[:3])
    if file_count > 3:
        listed = f'{listed}, ...'
    noun = 'file' if file_count == 1 else 'files'
    return f'Updated {file_count} {noun} ({listed}); +{additions}/-{deletions} changed lines.'


def _artifact_base(repo_hint: str) -> Path:
    candidate = Path(repo_hint).expanduser()
    if repo_hint and candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    return Path.cwd()


def _display_artifacts_dir(base: Path, artifacts_dir: Path) -> str:
    try:
        return str(artifacts_dir.relative_to(base))
    except ValueError:
        return str(artifacts_dir)


def _cleanup_artifacts(repo_hint: str, artifacts_dir: Path) -> None:
    repo_candidate = Path(repo_hint).expanduser()
    worktree_dir = artifacts_dir / 'worktree'
    if repo_hint and repo_candidate.exists() and (repo_candidate / '.git').exists() and worktree_dir.exists():
        subprocess.run(
            ['git', '-C', str(repo_candidate.resolve()), 'worktree', 'remove', '--force', str(worktree_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        subprocess.run(
            ['git', '-C', str(repo_candidate.resolve()), 'worktree', 'prune'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir, ignore_errors=True)


def _coerce_mapping(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
) -> MutableMapping[str, Any]:
    if value is None:
        if allow_none:
            return {}
        raise AdapterError(OPENCODE_EXEC_FAILED, f'{field_name} is required', {'field': field_name})
    if not isinstance(value, MutableMapping):
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            f'{field_name} must be an object',
            {'field': field_name, 'actual_type': type(value).__name__},
        )
    return value


def _validate_repo(repo_hint: str) -> Path:
    if not repo_hint:
        raise AdapterError(GIT_REPO_INVALID, 'repo_path is required', {'field': 'repo_path'})
    repo_root = Path(repo_hint).expanduser().resolve()
    if not repo_root.is_dir():
        raise AdapterError(GIT_REPO_INVALID, 'repo_path does not exist', {'repo_path': repo_hint})
    result = _run_command(['git', '-C', str(repo_root), 'rev-parse', '--is-inside-work-tree'], timeout=30)
    if result.returncode != 0 or result.stdout.strip() != 'true':
        raise AdapterError(
            GIT_REPO_INVALID,
            'repo_path is not a git repository',
            {'repo_path': str(repo_root), 'stderr': result.stderr.strip()},
        )
    return repo_root


def _resolve_base_commit(repo_root: Path, base_ref: str) -> str:
    result = _run_command(
        ['git', '-C', str(repo_root), 'rev-parse', '--verify', f'{base_ref}^{{commit}}'],
        timeout=30,
    )
    if result.returncode != 0:
        raise AdapterError(
            BASE_REF_INVALID,
            'base_ref could not be resolved to a commit',
            {'base_ref': base_ref, 'stderr': result.stderr.strip()},
        )
    return result.stdout.strip()


def _resolve_allowlist(repo_root: Path, code_context: Mapping[str, Any]) -> Tuple[List[str], Optional[str]]:
    target_value = str(code_context.get('target_file') or '').strip()
    related_files = code_context.get('related_files') or []
    if related_files and not isinstance(related_files, list):
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'code_context.related_files must be a list',
            {'field': 'code_context.related_files'},
        )
    ordered_paths: List[str] = []
    if target_value:
        ordered_paths.append(target_value)
    for item in related_files:
        if item is None:
            continue
        value = str(item).strip()
        if value:
            ordered_paths.append(value)
    if not ordered_paths:
        return [], None
    normalized: List[str] = []
    seen: Set[str] = set()
    for path_value in ordered_paths:
        relative_path = _normalize_repo_path(repo_root, path_value)
        if relative_path in seen:
            continue
        seen.add(relative_path)
        normalized.append(relative_path)
    normalized_target = _normalize_repo_path(repo_root, target_value) if target_value else None
    if normalized_target and not (repo_root / normalized_target).exists():
        raise AdapterError(
            TARGET_FILE_MISSING,
            'target_file does not exist in repo_path',
            {'target_file': normalized_target, 'repo_path': str(repo_root)},
        )
    return normalized, normalized_target


def _normalize_repo_path(repo_root: Path, path_value: str) -> str:
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (repo_root / candidate).resolve()
    try:
        relative = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise AdapterError(
            TARGET_FILE_MISSING,
            'allowlist path must stay inside repo_path',
            {'path': path_value, 'repo_path': str(repo_root)},
        ) from exc
    return relative.as_posix()


def _resolve_opencode_binary(payload: Mapping[str, Any]) -> str:
    options = _coerce_mapping(payload.get('opencode'), 'opencode', allow_none=True)
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
        raise AdapterError(
            OPENCODE_AUTH_MISSING,
            'opencode has no configured credentials',
            {'output': combined},
        )


def _create_worktree(repo_root: Path, base_commit: str, worktree_dir: Path) -> None:
    result = _run_command(
        ['git', '-C', str(repo_root), 'worktree', 'add', '--detach', str(worktree_dir), base_commit],
        timeout=60,
    )
    if result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to create isolated git worktree',
            {'stdout': result.stdout, 'stderr': result.stderr, 'base_commit': base_commit},
        )


def _validate_target_in_worktree(worktree_dir: Path, target_file: str) -> None:
    if not (worktree_dir / target_file).exists():
        raise AdapterError(
            TARGET_FILE_MISSING,
            'target_file does not exist in the isolated worktree',
            {'target_file': target_file, 'worktree': str(worktree_dir)},
        )


def _run_opencode(
    *,
    binary: str,
    worktree_dir: Path,
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
    result = _run_command(command, cwd=worktree_dir, timeout=timeout)
    events = parse_event_stream(result.stdout)
    if result.returncode != 0:
        error_event = extract_error_event(events)
        details: Dict[str, Any] = {
            'returncode': result.returncode,
            'stderr': result.stderr,
        }
        if error_event is not None:
            details['event'] = error_event
        raise AdapterError(OPENCODE_EXEC_FAILED, 'opencode run failed', details)
    return events, result.stderr


def _collect_changed_files(worktree_dir: Path) -> List[str]:
    tracked = _split_null_terminated(
        _run_command(['git', '-C', str(worktree_dir), 'diff', '--name-only', '-z', 'HEAD', '--'], timeout=30).stdout
    )
    untracked = _split_null_terminated(
        _run_command(
            ['git', '-C', str(worktree_dir), 'ls-files', '--others', '--exclude-standard', '-z'],
            timeout=30,
        ).stdout
    )
    return sorted(set(tracked) | set(untracked))


def _stage_and_collect_diff(worktree_dir: Path, changed_files: Iterable[str]) -> str:
    add_cmd = ['git', '-C', str(worktree_dir), 'add', '-A', '--', '.']
    add_result = _run_command(add_cmd, timeout=30)
    if add_result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to stage changed files for diff collection',
            {'stdout': add_result.stdout, 'stderr': add_result.stderr},
        )
    diff_result = _run_command(
        ['git', '-C', str(worktree_dir), 'diff', '--cached', '--binary', 'HEAD', '--'],
        timeout=30,
        text=False,
    )
    if diff_result.returncode != 0:
        raise AdapterError(
            OPENCODE_EXEC_FAILED,
            'failed to collect git diff',
            {
                'stdout': diff_result.stdout.decode('utf-8', errors='replace'),
                'stderr': diff_result.stderr.decode('utf-8', errors='replace'),
            },
        )
    return diff_result.stdout.decode('utf-8', errors='replace')


def _run_command(
    args: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    timeout: int,
    text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
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


def _split_null_terminated(output: str) -> List[str]:
    if not output:
        return []
    return [item for item in output.split('\0') if item]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def _write_jsonl(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    content = ''.join(f'{json.dumps(event, ensure_ascii=False)}\n' for event in events)
    path.write_text(content, encoding='utf-8')


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding='utf-8')
