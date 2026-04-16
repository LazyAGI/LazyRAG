from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Dict, List

from automation.opencode_adapter.errors import (
    AdapterError,
    OPENCODE_AUTH_MISSING,
    OPENCODE_BINARY_MISSING,
    OPENCODE_EXEC_FAILED,
    REPO_PATH_INVALID,
)
from automation.opencode_adapter.events import extract_error_event, extract_text, parse_event_stream


TASK_SCOPE_EMPTY = 'TASK_SCOPE_EMPTY'
TASK_SCOPE_FORBIDDEN = 'TASK_SCOPE_FORBIDDEN'
CONSTRAINTS_PARSE_FAILED = 'CONSTRAINTS_PARSE_FAILED'
REPORT_JSON_INVALID = 'REPORT_JSON_INVALID'
SCOPE_VIOLATION = 'SCOPE_VIOLATION'
NO_CHANGE = 'NO_CHANGE'

DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_ARTIFACT_ROOT = Path(tempfile.gettempdir()) / 'lazy-rag-edit'
DEFAULT_CLI_INSTRUCTION = '完成这个json内的任务'
SUCCESSFUL_STATUSES = {'SUCCEEDED', NO_CHANGE}
JSON_PATH_PATTERN = re.compile(r'(?P<path>(?:~|/|\./|\.\./)[^\s\'"“”‘’]+?\.json)')
ALLOWED_FILE_SCOPE_PATH = Path(__file__).with_name('allowed_file_scope.txt')
COPY_IGNORE_PATTERNS = ('.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '*.pyc', '*.pyo')
SNAPSHOT_IGNORE_NAMES = {'.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}


def execute_simple_report(
    payload: Mapping[str, Any],
    *,
    repo_path: str,
    instruction: str,
    opencode_options: Mapping[str, Any] | None = None,
    artifact_root: str | None = None,
) -> Dict[str, Any]:
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

        repo_root = _validate_repo_path(repo_path)
        allowed_files = _resolve_report_scope(report, _load_hard_allowlist())

        merged_opencode = _merge_opencode_options(
            _coerce_mapping(report.get('opencode'), 'opencode', allow_none=True),
            opencode_options or {},
        )
        binary = _resolve_opencode_binary(merged_opencode)
        _preflight_opencode(binary)

        repo_copy = run_root / 'repo_copy'
        _materialize_repo_copy(repo_root, repo_copy)
        before_snapshot = _build_directory_snapshot(repo_copy)

        prompt = _build_prompt(
            instruction=instruction,
            report=report,
            allowed_files=allowed_files,
        )
        _write_text(run_root / 'prompt.txt', prompt)

        events, stderr = _run_opencode(
            binary=binary,
            repo_copy=repo_copy,
            prompt=prompt,
            options=merged_opencode,
        )
        _write_jsonl(run_root / 'events.jsonl', events)
        _write_text(run_root / 'stderr.log', stderr)

        changed_files = _collect_changed_files(repo_copy, before_snapshot)
        violations = sorted(path for path in changed_files if path not in set(allowed_files))
        if violations:
            raise AdapterError(
                SCOPE_VIOLATION,
                'OpenCode modified files outside the allowed scope',
                {'violations': violations, 'allowed_files': allowed_files},
            )

        change_summary = extract_text(events) or _build_change_summary(changed_files)
        result = {
            'files_changed': changed_files,
            'change_summary': change_summary or 'No changes were necessary.',
        }

        outcome = {
            'status': 'SUCCEEDED' if changed_files else NO_CHANGE,
            'result': result,
            'error': None,
            'artifacts_dir': artifacts_dir,
        }
        _write_json(run_root / 'result.json', outcome)
        return outcome
    except AdapterError as exc:
        outcome = {
            'status': 'FAILED',
            'result': None,
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
            'result': None,
            'error': wrapped.to_payload(),
            'artifacts_dir': artifacts_dir,
        }
        if artifacts_dir:
            _write_json(Path(artifacts_dir) / 'result.json', outcome)
        return outcome


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


def _resolve_report_scope(report: Mapping[str, Any], hard_allowlist: Sequence[str]) -> List[str]:
    allowed_set = set(hard_allowlist)
    requested: List[str] = []
    seen: set[str] = set()
    forbidden: List[str] = []

    for task in _extract_tasks(report):
        raw_targets = task.get('change_targets') or []
        if not isinstance(raw_targets, list):
            raise AdapterError(
                REPORT_JSON_INVALID,
                'task.change_targets must be a list',
                {'task_id': str(task.get('task_id') or ''), 'field': 'change_targets'},
            )
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
            'report requested files outside the hard allowlist',
            {'forbidden_files': forbidden},
        )
    if not requested:
        raise AdapterError(TASK_SCOPE_EMPTY, 'report has no allowed change_targets', {})
    return requested


def _build_prompt(
    *,
    instruction: str,
    report: Mapping[str, Any],
    allowed_files: Sequence[str],
) -> str:
    scope_lines = '\n'.join(f'- {path}' for path in allowed_files)
    return textwrap.dedent(
        f"""
        You are editing a copied repository, not the original repository.

        Perform one single-pass code edit for the provided report.
        Do not do any task orchestration, retries, validation loops, or test execution.
        Keep the implementation minimal and directly tied to the report.

        User instruction:
        {instruction}

        Hard constraints:
        - Only modify files in this allowlist:
        {scope_lines}
        - Do not modify any other file, even if the report mentions it.
        - The host will reject any out-of-scope file modification.
        - End with a concise plain-text change summary in 1-3 sentences.

        Report JSON:
        {json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)}
        """
    ).strip()


def _validate_repo_path(repo_path: str) -> Path:
    if not repo_path:
        raise AdapterError(REPO_PATH_INVALID, 'repo path is required', {'field': 'repo_path'})
    repo_root = Path(repo_path).expanduser().resolve()
    if not repo_root.is_dir():
        raise AdapterError(REPO_PATH_INVALID, 'repo path does not exist', {'repo_path': repo_path})
    return repo_root


def _load_hard_allowlist() -> List[str]:
    if not ALLOWED_FILE_SCOPE_PATH.is_file():
        raise AdapterError(
            CONSTRAINTS_PARSE_FAILED,
            'allowed file scope document was not found',
            {'path': str(ALLOWED_FILE_SCOPE_PATH)},
        )

    items: List[str] = []
    seen: set[str] = set()
    _line_number = 0
    for _line_number, raw_line in enumerate(
        ALLOWED_FILE_SCOPE_PATH.read_text(encoding='utf-8').splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        normalized = _normalize_relative_path(line)
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)

    if not items:
        raise AdapterError(
            CONSTRAINTS_PARSE_FAILED,
            'allowed file scope document is empty',
            {'path': str(ALLOWED_FILE_SCOPE_PATH), 'line_number': _line_number},
        )
    return items


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


def _materialize_repo_copy(repo_root: Path, target_dir: Path) -> None:
    shutil.copytree(repo_root, target_dir, ignore=_build_copy_ignore(target_dir))


def _build_copy_ignore(target_dir: Path):
    pattern_ignore = shutil.ignore_patterns(*COPY_IGNORE_PATTERNS)
    target_dir = target_dir.resolve()

    def _ignore(current_dir: str, names: list[str]) -> set[str]:
        ignored = set(pattern_ignore(current_dir, names))
        current_path = Path(current_dir).resolve()
        for name in names:
            child_path = (current_path / name).resolve()
            if child_path == target_dir or target_dir.is_relative_to(child_path):
                ignored.add(name)
        return ignored

    return _ignore


def _build_directory_snapshot(root: Path) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(part in SNAPSHOT_IGNORE_NAMES for part in relative.parts):
            continue
        if path.is_dir():
            continue
        snapshot[relative.as_posix()] = _hash_file(path)
    return snapshot


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _run_opencode(
    *,
    binary: str,
    repo_copy: Path,
    prompt: str,
    options: Mapping[str, Any],
) -> tuple[List[Dict[str, Any]], str]:
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


def _collect_changed_files(repo_copy: Path, before_snapshot: Mapping[str, str]) -> List[str]:
    after_snapshot = _build_directory_snapshot(repo_copy)
    changed = {
        path
        for path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(path) != after_snapshot.get(path)
    }
    return sorted(changed)


def _build_change_summary(files_changed: Sequence[str]) -> str:
    if not files_changed:
        return 'No changes were necessary.'
    listed = ', '.join(files_changed[:3])
    if len(files_changed) > 3:
        listed = f'{listed}, ...'
    noun = 'file' if len(files_changed) == 1 else 'files'
    return f'Updated {len(files_changed)} {noun}: {listed}.'


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
        raise AdapterError(
            TASK_SCOPE_FORBIDDEN,
            'absolute file paths are not allowed in task scope',
            {'path': path_value},
        )
    normalized = candidate.as_posix().strip('/')
    if not normalized or normalized.startswith('../') or '/..' in normalized:
        raise AdapterError(
            TASK_SCOPE_FORBIDDEN,
            'task scope path must stay inside the repository',
            {'path': path_value},
        )
    return normalized


def _sanitize_identifier(value: str, *, fallback: str) -> str:
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', value).strip('_')
    return sanitized or fallback


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


def _extract_json_path_from_text(text: str | None) -> Path | None:
    if not text:
        return None
    for match in JSON_PATH_PATTERN.finditer(text):
        raw_path = match.group('path').rstrip(')]}>,，。！？；;:')
        candidate = _existing_file_path(raw_path)
        if candidate is not None:
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

    embedded_path = _extract_json_path_from_text(positional_input)
    if embedded_path is not None:
        return embedded_path

    raise AdapterError(
        REPORT_JSON_INVALID,
        (
            'report json path is required; pass --report-json, provide the '
            'json path directly, or include it in the natural-language input'
        ),
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
            embedded_path = _extract_json_path_from_text(positional_input)
            if (
                embedded_path is None
                or embedded_path != report_json_path
                or positional_input.strip() != str(report_json_path)
            ):
                return positional_input.strip()

    return DEFAULT_CLI_INSTRUCTION


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

    cwd_path = Path.cwd().resolve()
    if cwd_path.is_dir():
        return str(cwd_path)

    return str(report_json_path.parent.resolve())


def _render_outcome(outcome: Mapping[str, Any], *, pretty: bool, output_path: str | None) -> int:
    rendered = json.dumps(outcome, ensure_ascii=False, indent=2 if pretty else None)
    print(rendered)
    if output_path:
        Path(output_path).write_text(rendered + '\n', encoding='utf-8')
    return 0 if outcome.get('status') in SUCCESSFUL_STATUSES else 1


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the simplified OpenCode report runner.')
    parser.add_argument(
        'input',
        nargs='?',
        help='Path to the upstream report JSON file, or natural-language input that includes the report JSON path.',
    )
    parser.add_argument('--instruction', help='Optional natural-language instruction. Defaults to 完成这个json内的任务.')
    parser.add_argument('--report-json', help='Path to the upstream report JSON file.')
    parser.add_argument('--repo', help='Path to the repository to copy and edit.')
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
            'result': None,
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
        opencode_options=opencode_options,
        artifact_root=args.artifact_root,
    )
    return _render_outcome(outcome, pretty=args.pretty, output_path=args.output)


if __name__ == '__main__':
    raise SystemExit(main())
