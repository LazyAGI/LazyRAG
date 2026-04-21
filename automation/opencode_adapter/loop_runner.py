from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import MutableMapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from algorithm.evo.output.test_log_collector import check_pytest_log_passed
from automation.opencode_adapter.errors import (
    AdapterError,
    INTERVENTION_REQUIRED,
    OPENCODE_EXEC_FAILED,
    REPO_PATH_INVALID,
    RESUME_BUNDLE_INVALID,
)
from automation.opencode_adapter.intervention import (
    HANDOFF_JSON_FILENAME,
    HANDOFF_MARKDOWN_FILENAME,
    LoopFailureSummary,
)


LOOP_CLI_FAILED = 'LOOP_CLI_FAILED'
LOOP_ARTIFACT_MISSING = 'LOOP_ARTIFACT_MISSING'
MAX_ROUNDS_EXCEEDED = 'MAX_ROUNDS_EXCEEDED'
REPORT_JSON_INVALID = 'REPORT_JSON_INVALID'
RUN_META_INVALID = 'RUN_META_INVALID'
DEFAULT_MAX_ROUNDS = 3
DEFAULT_TESTS_PATH = None
DEFAULT_TEST_COMMAND = ('bash', 'tests/run-all.sh')
DEFAULT_LOOP_ARTIFACT_ROOT = Path(tempfile.gettempdir()) / 'lazy-rag-loop'
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path('algorithm/evo/output')
OUTPUT_REPORTS_DIR = OUTPUT_ROOT / 'reports'
OUTPUT_VAL_DIR = OUTPUT_ROOT / 'val'
META_FILENAME = 'run.meta.json'
LOOP_RESULT_FILENAME = 'loop.result.json'
SOURCE_REPORT_FILENAME = 'source.report.json'
BASELINE_REPO_DIRNAME = 'baseline_repo'
CLI_ARTIFACTS_DIRNAME = 'cli_runs'
RUNNING_STATUS = 'RUNNING'
SUCCEEDED_STATUS = 'SUCCEEDED'
FAILED_STATUS = 'FAILED'
STAGE_INITIALIZED = 'initialized'
STAGE_CLI_RUNNING = 'cli_running'
STAGE_CLI_DONE = 'cli_done'
STAGE_TEST_RUNNING = 'test_running'
STAGE_TEST_DONE = 'test_done'
STAGE_INTERVENTION_REQUIRED = 'intervention_required'
STAGE_FINISHED = 'finished'
RESUME_MODE_CONTINUE = 'continue'
RESUME_MODE_ROLLBACK = 'rollback'
TERMINAL_STATUSES = {SUCCEEDED_STATUS, FAILED_STATUS, INTERVENTION_REQUIRED}
COPY_IGNORE_PATTERNS = (
    '.git',
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '*.pyc',
    '*.pyo',
)


def run_report_fix_loop(
    report_json_path: str | None = None,
    repo_path: str | None = None,
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    tests_path: str | None = DEFAULT_TESTS_PATH,
    test_command: Sequence[str] | None = None,
    artifact_root: str | None = None,
    python_executable: str | None = None,
    resume_bundle: str | None = None,
    resume_mode: str = RESUME_MODE_CONTINUE,
    extra_instruction: str | None = None,
) -> Dict[str, Any]:
    bundle_root: Path | None = None
    try:
        if max_rounds < 1:
            raise AdapterError(REPORT_JSON_INVALID, 'max_rounds must be at least 1', {'max_rounds': max_rounds})

        python_bin = python_executable or sys.executable
        if resume_bundle:
            bundle_root, _meta = _resume_bundle(
                resume_bundle=resume_bundle,
                report_json_path=report_json_path,
                repo_path=repo_path,
                max_rounds=max_rounds,
                tests_path=tests_path,
                test_command=test_command,
                python_executable=python_bin,
                resume_mode=resume_mode,
                extra_instruction=extra_instruction,
            )
        else:
            report_path = _validate_report_json_path(report_json_path or '')
            repo_root = _validate_repo_path(repo_path or '')
            bundle_root = _initialize_bundle(
                report_path=report_path,
                repo_root=repo_root,
                max_rounds=max_rounds,
                tests_path=tests_path,
                test_command=test_command,
                artifact_root=artifact_root,
                python_executable=python_bin,
                extra_instruction=extra_instruction,
            )
        return _run_loop(bundle_root)
    except AdapterError as exc:
        return _build_loop_outcome(
            status=FAILED_STATUS,
            bundle_dir=bundle_root,
            rounds=[],
            last_result=None,
            error=exc.to_payload(),
            final_repo='',
            intervention=None,
        )
    except Exception as exc:
        wrapped = AdapterError(OPENCODE_EXEC_FAILED, 'unexpected loop runner failure', {'error': str(exc)})
        if bundle_root and bundle_root.is_dir():
            meta = _safe_load_meta(bundle_root)
            if meta is not None and str(meta.get('status') or '') not in TERMINAL_STATUSES:
                meta['status'] = FAILED_STATUS
                meta['active_stage'] = STAGE_FINISHED
                meta['error'] = wrapped.to_payload()
                _save_meta(bundle_root, meta)
                return _build_outcome_from_meta(bundle_root, meta)
        return _build_loop_outcome(
            status=FAILED_STATUS,
            bundle_dir=bundle_root,
            rounds=[],
            last_result=None,
            error=wrapped.to_payload(),
            final_repo='',
            intervention=None,
        )


def _initialize_bundle(
    *,
    report_path: Path,
    repo_root: Path,
    max_rounds: int,
    tests_path: str | None,
    test_command: Sequence[str] | None,
    artifact_root: str | None,
    python_executable: str,
    extra_instruction: str | None,
) -> Path:
    report = _load_report(report_path)
    report_id = str(report.get('report_id') or report_path.stem or 'report').strip() or 'report'

    artifact_base = Path(artifact_root).expanduser() if artifact_root else DEFAULT_LOOP_ARTIFACT_ROOT
    artifact_base.mkdir(parents=True, exist_ok=True)
    bundle_root = Path(
        tempfile.mkdtemp(prefix=f'{_sanitize_identifier(report_id)}_', dir=str(artifact_base.resolve()))
    ).resolve()

    source_report_path = bundle_root / SOURCE_REPORT_FILENAME
    shutil.copy2(report_path, source_report_path)

    baseline_repo_dir = bundle_root / BASELINE_REPO_DIRNAME
    _copy_repo_tree(repo_root, baseline_repo_dir)

    command = _resolve_test_command(
        tests_path=tests_path,
        test_command=test_command,
        python_executable=python_executable,
    )
    now = _utcnow()
    meta: Dict[str, Any] = {
        'version': '1.0',
        'report_id': report_id,
        'bundle_dir': str(bundle_root),
        'original_report_json_path': str(report_path),
        'original_repo_path': str(repo_root),
        'source_report_path': str(source_report_path),
        'baseline_repo_dir': str(baseline_repo_dir),
        'current_repo_dir': str(baseline_repo_dir),
        'tests_path': tests_path or '',
        'test_command': command,
        'python_executable': python_executable,
        'status': RUNNING_STATUS,
        'active_stage': STAGE_INITIALIZED,
        'active_round': 1,
        'session_round_start': 0,
        'session_round_limit': max_rounds,
        'pending_extra_instruction': str(extra_instruction or '').strip(),
        'rounds': [],
        'last_result': None,
        'error': None,
        'intervention': None,
        'created_at': now,
        'updated_at': now,
    }
    _save_meta(bundle_root, meta)
    return bundle_root


def _resume_bundle(
    *,
    resume_bundle: str,
    report_json_path: str | None,
    repo_path: str | None,
    max_rounds: int,
    tests_path: str | None,
    test_command: Sequence[str] | None,
    python_executable: str,
    resume_mode: str,
    extra_instruction: str | None,
) -> tuple[Path, Dict[str, Any]]:
    bundle_root = Path(resume_bundle).expanduser().resolve()
    if not bundle_root.is_dir():
        raise AdapterError(
            RESUME_BUNDLE_INVALID,
            'resume bundle directory does not exist',
            {'resume_bundle': str(bundle_root)},
        )

    meta = _load_meta(bundle_root)
    _validate_resume_bundle_paths(meta)
    _validate_resume_inputs(meta, report_json_path, repo_path)

    command = _resolve_test_command(
        tests_path=tests_path or str(meta.get('tests_path') or '') or None,
        test_command=test_command or meta.get('test_command') or None,
        python_executable=python_executable,
    )
    meta['tests_path'] = tests_path if tests_path is not None else str(meta.get('tests_path') or '')
    meta['test_command'] = command
    meta['python_executable'] = python_executable

    if str(meta.get('status') or '') == INTERVENTION_REQUIRED:
        if resume_mode not in {RESUME_MODE_CONTINUE, RESUME_MODE_ROLLBACK}:
            raise AdapterError(
                RESUME_BUNDLE_INVALID,
                'resume_mode must be "continue" or "rollback"',
                {'resume_mode': resume_mode},
            )
        if resume_mode == RESUME_MODE_ROLLBACK:
            next_repo_dir = str(meta.get('baseline_repo_dir') or '')
        else:
            next_repo_dir = str(meta.get('current_repo_dir') or '')
        if not Path(next_repo_dir).is_dir():
            raise AdapterError(
                RESUME_BUNDLE_INVALID,
                'resume base repo is missing from the bundle',
                {'repo_dir': next_repo_dir, 'resume_mode': resume_mode},
            )
        meta['status'] = RUNNING_STATUS
        meta['active_stage'] = STAGE_INITIALIZED
        meta['active_round'] = len(meta.get('rounds') or []) + 1
        meta['session_round_start'] = len(meta.get('rounds') or [])
        meta['session_round_limit'] = len(meta.get('rounds') or []) + max_rounds
        meta['current_repo_dir'] = next_repo_dir
        meta['pending_extra_instruction'] = str(extra_instruction or '').strip()
        meta['intervention'] = None
        meta['error'] = None
    elif str(meta.get('status') or '') in {SUCCEEDED_STATUS, FAILED_STATUS}:
        raise AdapterError(
            RESUME_BUNDLE_INVALID,
            'bundle is already in a terminal state and cannot be resumed',
            {'status': meta.get('status')},
        )
    elif extra_instruction and str(extra_instruction).strip():
        meta['pending_extra_instruction'] = str(extra_instruction).strip()

    _save_meta(bundle_root, meta)
    return bundle_root, meta


def _run_loop(bundle_root: Path) -> Dict[str, Any]:
    while True:
        meta = _load_meta(bundle_root)
        status = str(meta.get('status') or RUNNING_STATUS)
        stage = str(meta.get('active_stage') or STAGE_INITIALIZED)

        if status in TERMINAL_STATUSES or stage in {STAGE_FINISHED, STAGE_INTERVENTION_REQUIRED}:
            return _build_outcome_from_meta(bundle_root, meta)

        round_index = int(meta.get('active_round') or len(meta.get('rounds') or []) + 1)
        round_dir = bundle_root / f'round_{round_index}'

        if stage == STAGE_INITIALIZED:
            if round_index > int(meta.get('session_round_limit') or round_index):
                return _mark_intervention_required(bundle_root, meta, MAX_ROUNDS_EXCEEDED)

            round_state = _ensure_round_state(meta, round_index)
            round_state['base_repo_dir'] = str(
                round_state.get('base_repo_dir')
                or meta.get('current_repo_dir')
                or meta.get('baseline_repo_dir')
                or ''
            )
            _ensure_round_instruction(meta, bundle_root, round_index)
            round_state['status'] = 'RUNNING'
            meta['active_round'] = round_index
            meta['active_stage'] = STAGE_CLI_RUNNING
            _save_meta(bundle_root, meta)
            continue

        if stage == STAGE_CLI_RUNNING:
            round_state = _ensure_round_state(meta, round_index)
            instruction_path = Path(str(round_state.get('instruction_path') or round_dir / 'instruction.txt'))
            instruction = instruction_path.read_text(encoding='utf-8')
            base_repo_dir = Path(str(round_state.get('base_repo_dir') or meta.get('current_repo_dir') or '')).resolve()
            if not base_repo_dir.is_dir():
                return _mark_failed(
                    bundle_root,
                    meta,
                    {
                        'code': REPO_PATH_INVALID,
                        'message': 'base repo for the current round does not exist',
                        'details': {'round': round_index, 'repo_dir': str(base_repo_dir)},
                    },
                )

            cli_result = _run_cli_once(
                report_json_path=Path(str(meta.get('source_report_path') or '')),
                repo_path=base_repo_dir,
                instruction=instruction,
                artifact_root=bundle_root / CLI_ARTIFACTS_DIRNAME,
                python_executable=str(meta.get('python_executable') or sys.executable),
            )
            _write_text(round_dir / 'cli.stdout.json', cli_result['stdout'])
            _write_text(round_dir / 'cli.stderr.log', cli_result['stderr'])
            _write_json(round_dir / 'cli.result.json', cli_result['payload'])

            round_state['instruction_path'] = str(instruction_path)
            round_state['cli_stdout_path'] = str(round_dir / 'cli.stdout.json')
            round_state['cli_stderr_path'] = str(round_dir / 'cli.stderr.log')
            round_state['cli_result_path'] = str(round_dir / 'cli.result.json')
            round_state['cli_artifacts_dir'] = str(cli_result['payload'].get('artifacts_dir') or '')
            round_state['cli_status'] = str(cli_result['payload'].get('status') or '')
            round_state['cli_error'] = cli_result['payload'].get('error')

            result_payload = cli_result['payload'].get('result') if isinstance(cli_result['payload'].get('result'), dict) else {}
            round_state['files_changed'] = list(result_payload.get('files_changed') or [])
            round_state['change_summary'] = str(result_payload.get('change_summary') or '')
            meta['last_result'] = result_payload or None

            if cli_result['payload'].get('status') == FAILED_STATUS:
                round_state['status'] = FAILED_STATUS
                return _mark_failed(
                    bundle_root,
                    meta,
                    {
                        'code': LOOP_CLI_FAILED,
                        'message': 'cli execution failed inside the fix loop',
                        'details': {'round': round_index, 'cli_error': cli_result['payload'].get('error')},
                    },
                )

            repo_copy = Path(str(cli_result['payload'].get('artifacts_dir') or '')).resolve() / 'repo_copy'
            if not repo_copy.is_dir():
                round_state['status'] = FAILED_STATUS
                return _mark_failed(
                    bundle_root,
                    meta,
                    {
                        'code': LOOP_ARTIFACT_MISSING,
                        'message': 'repo_copy was not found after cli execution',
                        'details': {'round': round_index, 'artifacts_dir': cli_result['payload'].get('artifacts_dir')},
                    },
                )

            repo_reports_dir, _repo_val_dir = _ensure_output_dirs(repo_copy)
            report_copy_path = repo_reports_dir / 'source.report.json'
            shutil.copy2(Path(str(meta.get('source_report_path') or '')), report_copy_path)

            round_state['report_copy_path'] = str(report_copy_path)
            round_state['repo_copy_dir'] = str(repo_copy)
            round_state['status'] = 'CLI_DONE'
            meta['current_repo_dir'] = str(repo_copy)
            meta['active_stage'] = STAGE_CLI_DONE
            _save_meta(bundle_root, meta)
            continue

        if stage in {STAGE_CLI_DONE, STAGE_TEST_RUNNING}:
            round_state = _ensure_round_state(meta, round_index)
            repo_copy_dir = Path(str(round_state.get('repo_copy_dir') or meta.get('current_repo_dir') or '')).resolve()
            if not repo_copy_dir.is_dir():
                return _mark_failed(
                    bundle_root,
                    meta,
                    {
                        'code': LOOP_ARTIFACT_MISSING,
                        'message': 'repo_copy was not found before test execution',
                        'details': {'round': round_index, 'repo_copy_dir': str(repo_copy_dir)},
                    },
                )

            _repo_reports_dir, repo_val_dir = _ensure_output_dirs(repo_copy_dir)
            meta['active_stage'] = STAGE_TEST_RUNNING
            _save_meta(bundle_root, meta)

            test_result = _run_tests_once(
                repo_copy=repo_copy_dir,
                output_val_dir=repo_val_dir,
                tests_path=str(meta.get('tests_path') or '') or None,
                test_command=meta.get('test_command') or None,
                python_executable=str(meta.get('python_executable') or sys.executable),
            )
            _write_json(round_dir / 'test.result.json', test_result)

            round_state['test_result_path'] = str(round_dir / 'test.result.json')
            round_state['test_log_path'] = str(test_result['log_path'])
            round_state['test_status'] = str(test_result['status'] or '')
            round_state['status'] = 'PASSED' if test_result['status'] == 'PASSED' else FAILED_STATUS
            meta['active_stage'] = STAGE_TEST_DONE
            _save_meta(bundle_root, meta)
            continue

        if stage == STAGE_TEST_DONE:
            round_state = _ensure_round_state(meta, round_index)
            if str(round_state.get('test_status') or '') == 'PASSED':
                meta['status'] = SUCCEEDED_STATUS
                meta['active_stage'] = STAGE_FINISHED
                meta['error'] = None
                meta['intervention'] = None
                _save_meta(bundle_root, meta)
                return _build_outcome_from_meta(bundle_root, meta)

            if round_index >= int(meta.get('session_round_limit') or round_index):
                return _mark_intervention_required(bundle_root, meta, MAX_ROUNDS_EXCEEDED)

            meta['active_round'] = round_index + 1
            meta['active_stage'] = STAGE_INITIALIZED
            meta['current_repo_dir'] = str(round_state.get('repo_copy_dir') or meta.get('current_repo_dir') or '')
            _save_meta(bundle_root, meta)
            continue

        raise AdapterError(
            RUN_META_INVALID,
            'run meta contains an unsupported stage',
            {'active_stage': stage, 'bundle_dir': str(bundle_root)},
        )


def _mark_failed(bundle_root: Path, meta: Dict[str, Any], error: Dict[str, Any]) -> Dict[str, Any]:
    meta['status'] = FAILED_STATUS
    meta['active_stage'] = STAGE_FINISHED
    meta['error'] = error
    _save_meta(bundle_root, meta)
    return _build_outcome_from_meta(bundle_root, meta)


def _mark_intervention_required(bundle_root: Path, meta: Dict[str, Any], reason: str) -> Dict[str, Any]:
    summary = LoopFailureSummary(bundle_root, meta)
    handoff_payload = summary.export_handoff()
    intervention = {
        'reason': reason,
        'resume_modes': [RESUME_MODE_CONTINUE, RESUME_MODE_ROLLBACK],
        'handoff_json_path': str(bundle_root / HANDOFF_JSON_FILENAME),
        'handoff_markdown_path': str(bundle_root / HANDOFF_MARKDOWN_FILENAME),
        'baseline_repo_dir': str(meta.get('baseline_repo_dir') or ''),
        'current_repo_dir': str(meta.get('current_repo_dir') or ''),
        'next_suggestion': handoff_payload.get('next_suggestion'),
        'user_prompt_draft': handoff_payload.get('user_prompt_draft'),
    }
    meta['status'] = INTERVENTION_REQUIRED
    meta['active_stage'] = STAGE_INTERVENTION_REQUIRED
    meta['intervention'] = intervention
    meta['error'] = {
        'code': INTERVENTION_REQUIRED,
        'message': 'manual intervention is required before more fix rounds can continue',
        'details': {
            'reason': reason,
            'total_rounds': len(meta.get('rounds') or []),
            'handoff_json_path': intervention['handoff_json_path'],
            'handoff_markdown_path': intervention['handoff_markdown_path'],
        },
    }
    _save_meta(bundle_root, meta)
    return _build_outcome_from_meta(bundle_root, meta)


def _validate_report_json_path(report_json_path: str) -> Path:
    candidate = Path(report_json_path).expanduser().resolve()
    if not candidate.is_file():
        raise AdapterError(REPORT_JSON_INVALID, 'report json file was not found', {'path': str(candidate)})
    return candidate


def _validate_repo_path(repo_path: str) -> Path:
    if not repo_path:
        raise AdapterError(REPO_PATH_INVALID, 'repo path is required', {'field': 'repo_path'})
    candidate = Path(repo_path).expanduser().resolve()
    if not candidate.is_dir():
        raise AdapterError(REPO_PATH_INVALID, 'repo path does not exist', {'repo_path': str(candidate)})
    return candidate


def _load_report(report_path: Path) -> Dict[str, Any]:
    loaded = json.loads(report_path.read_text(encoding='utf-8'))
    if not isinstance(loaded, dict):
        raise AdapterError(REPORT_JSON_INVALID, 'report json root must be an object', {'path': str(report_path)})
    return loaded


def _load_meta(bundle_dir: Path) -> Dict[str, Any]:
    meta_path = bundle_dir / META_FILENAME
    if not meta_path.is_file():
        raise AdapterError(
            RESUME_BUNDLE_INVALID,
            'resume bundle does not contain run.meta.json',
            {'bundle_dir': str(bundle_dir)},
        )
    loaded = json.loads(meta_path.read_text(encoding='utf-8'))
    if not isinstance(loaded, MutableMapping):
        raise AdapterError(RUN_META_INVALID, 'run.meta.json root must be an object', {'path': str(meta_path)})
    if not isinstance(loaded.get('rounds'), list):
        raise AdapterError(RUN_META_INVALID, 'run.meta.json rounds must be a list', {'path': str(meta_path)})
    return dict(loaded)


def _safe_load_meta(bundle_dir: Path) -> Dict[str, Any] | None:
    try:
        return _load_meta(bundle_dir)
    except Exception:
        return None


def _save_meta(bundle_dir: Path, meta: Dict[str, Any]) -> None:
    meta_path = bundle_dir / META_FILENAME
    payload = dict(meta)
    payload['updated_at'] = _utcnow()
    temp_path = meta_path.with_suffix('.tmp')
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    temp_path.replace(meta_path)


def _validate_resume_bundle_paths(meta: Dict[str, Any]) -> None:
    source_report_path = Path(str(meta.get('source_report_path') or ''))
    baseline_repo_dir = Path(str(meta.get('baseline_repo_dir') or ''))
    if not source_report_path.is_file():
        raise AdapterError(
            RESUME_BUNDLE_INVALID,
            'bundle source report is missing',
            {'source_report_path': str(source_report_path)},
        )
    if not baseline_repo_dir.is_dir():
        raise AdapterError(
            RESUME_BUNDLE_INVALID,
            'bundle baseline repo is missing',
            {'baseline_repo_dir': str(baseline_repo_dir)},
        )


def _validate_resume_inputs(meta: Dict[str, Any], report_json_path: str | None, repo_path: str | None) -> None:
    if report_json_path:
        expected = str(_validate_report_json_path(report_json_path))
        actual = str(Path(str(meta.get('original_report_json_path') or '')).expanduser().resolve())
        if actual and expected != actual:
            raise AdapterError(
                RESUME_BUNDLE_INVALID,
                'resume bundle was created from a different report json path',
                {'expected': actual, 'received': expected},
            )

    if repo_path:
        expected = str(_validate_repo_path(repo_path))
        actual = str(Path(str(meta.get('original_repo_path') or '')).expanduser().resolve())
        if actual and expected != actual:
            raise AdapterError(
                RESUME_BUNDLE_INVALID,
                'resume bundle was created from a different repo path',
                {'expected': actual, 'received': expected},
            )


def _ensure_round_instruction(meta: Dict[str, Any], bundle_root: Path, round_index: int) -> str:
    round_state = _ensure_round_state(meta, round_index)
    round_dir = bundle_root / f'round_{round_index}'
    instruction_path = Path(str(round_state.get('instruction_path') or round_dir / 'instruction.txt'))
    if instruction_path.is_file():
        round_state['instruction_path'] = str(instruction_path)
        return instruction_path.read_text(encoding='utf-8')

    previous_cli_result = _previous_round_cli_payload(meta, round_index)
    previous_test_log = _previous_round_test_log(meta, round_index)
    extra_instruction = str(meta.get('pending_extra_instruction') or '').strip()
    instruction = _build_round_instruction(
        round_index=round_index,
        previous_cli_result=previous_cli_result,
        previous_test_log=previous_test_log,
        extra_instruction=extra_instruction,
    )
    _write_text(instruction_path, instruction)
    round_state['instruction_path'] = str(instruction_path)
    if extra_instruction:
        round_state['extra_instruction'] = extra_instruction
        meta['pending_extra_instruction'] = ''
    return instruction


def _previous_round_cli_payload(meta: Dict[str, Any], round_index: int) -> Dict[str, Any] | None:
    if round_index <= 1:
        return None
    round_state = _find_round_state(meta, round_index - 1)
    if round_state is None:
        return None
    cli_result_path = Path(str(round_state.get('cli_result_path') or ''))
    if cli_result_path.is_file():
        loaded = json.loads(cli_result_path.read_text(encoding='utf-8'))
        return loaded if isinstance(loaded, dict) else None
    return None


def _previous_round_test_log(meta: Dict[str, Any], round_index: int) -> str:
    if round_index <= 1:
        return ''
    round_state = _find_round_state(meta, round_index - 1)
    if round_state is None:
        return ''
    test_log_path = Path(str(round_state.get('test_log_path') or ''))
    if not test_log_path.is_file():
        return ''
    return test_log_path.read_text(encoding='utf-8')


def _build_round_instruction(
    *,
    round_index: int,
    previous_cli_result: Dict[str, Any] | None,
    previous_test_log: str,
    extra_instruction: str,
) -> str:
    extra_block = ''
    if extra_instruction:
        extra_block = textwrap.dedent(
            f"""
            Extra user guidance:
            {extra_instruction}
            """
        ).strip()

    if round_index == 1 and not previous_test_log:
        sections = [
            textwrap.dedent(
                """
                根据 report 做一次最小修改。
                只修改 allowlist 范围内的必要文件。
                不要做无关重构，不要扩大改动范围。
                """
            ).strip()
        ]
        if extra_block:
            sections.append(extra_block)
        return '\n\n'.join(sections)

    previous_result = json.dumps(previous_cli_result or {}, ensure_ascii=False, indent=2, sort_keys=True)
    sections = [
        textwrap.dedent(
            f"""
            根据上一轮测试失败日志继续修复。
            只修复日志暴露的问题，不要扩大改动范围，不要修改 allowlist 之外的文件。

            上一轮 CLI 结果:
            {previous_result}

            TEST FAILURE LOG:
            {previous_test_log}
            """
        ).strip()
    ]
    if extra_block:
        sections.append(extra_block)
    return '\n\n'.join(sections)


def _run_cli_once(
    *,
    report_json_path: Path,
    repo_path: Path,
    instruction: str,
    artifact_root: Path,
    python_executable: str,
) -> Dict[str, Any]:
    env = os.environ.copy()
    package_root = str(PACKAGE_ROOT)
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f'{package_root}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else package_root

    result = subprocess.run(
        [
            python_executable,
            '-m',
            'automation.opencode_adapter.cli',
            str(report_json_path),
            '--repo',
            str(repo_path),
            '--instruction',
            instruction,
            '--artifact-root',
            str(artifact_root),
        ],
        cwd=str(PACKAGE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            LOOP_CLI_FAILED,
            'cli returned invalid json',
            {'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode},
        ) from exc

    if not isinstance(payload, dict):
        raise AdapterError(
            LOOP_CLI_FAILED,
            'cli returned a non-object payload',
            {'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode},
        )

    return {
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'payload': payload,
    }


def _run_tests_once(
    *,
    repo_copy: Path,
    output_val_dir: Path,
    tests_path: str | None,
    test_command: Sequence[str] | None,
    python_executable: str,
) -> Dict[str, Any]:
    command = _resolve_test_command(
        tests_path=tests_path,
        test_command=test_command,
        python_executable=python_executable,
    )
    result = subprocess.run(
        command,
        cwd=str(repo_copy),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    log = '\n'.join(part for part in [result.stdout, result.stderr] if part).strip()
    log_path = output_val_dir / 'test.log'
    _write_text(log_path, log)
    passed = check_pytest_log_passed(log_path=log_path)
    return {
        'status': 'PASSED' if passed else FAILED_STATUS,
        'returncode': result.returncode,
        'command': command,
        'log': log,
        'log_path': str(log_path),
    }


def _resolve_test_command(
    *,
    tests_path: str | None,
    test_command: Sequence[str] | None,
    python_executable: str,
) -> List[str]:
    if test_command:
        return [str(part) for part in test_command]
    if tests_path and tests_path.strip():
        return [python_executable, '-m', 'pytest', tests_path]
    return list(DEFAULT_TEST_COMMAND)


def _ensure_output_dirs(repo_copy: Path) -> tuple[Path, Path]:
    reports_dir = repo_copy / OUTPUT_REPORTS_DIR
    val_dir = repo_copy / OUTPUT_VAL_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir, val_dir


def _copy_repo_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*COPY_IGNORE_PATTERNS))


def _ensure_round_state(meta: Dict[str, Any], round_index: int) -> Dict[str, Any]:
    existing = _find_round_state(meta, round_index)
    if existing is not None:
        return existing
    created: Dict[str, Any] = {'round': round_index}
    rounds = meta.setdefault('rounds', [])
    if not isinstance(rounds, list):
        raise AdapterError(RUN_META_INVALID, 'run meta rounds must be a list', {})
    rounds.append(created)
    return created


def _find_round_state(meta: Dict[str, Any], round_index: int) -> Dict[str, Any] | None:
    for item in meta.get('rounds') or []:
        if isinstance(item, MutableMapping) and int(item.get('round') or 0) == round_index:
            return dict(item) if not isinstance(item, dict) else item
    return None


def _build_outcome_from_meta(bundle_root: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
    return _build_loop_outcome(
        status=str(meta.get('status') or FAILED_STATUS),
        bundle_dir=bundle_root,
        rounds=meta.get('rounds') or [],
        last_result=meta.get('last_result'),
        error=meta.get('error'),
        final_repo=str(meta.get('current_repo_dir') or ''),
        intervention=meta.get('intervention'),
    )


def _build_loop_outcome(
    *,
    status: str,
    bundle_dir: Path | None,
    rounds: Sequence[Dict[str, Any]],
    last_result: Dict[str, Any] | None,
    error: Dict[str, Any] | None,
    final_repo: str,
    intervention: Dict[str, Any] | None,
) -> Dict[str, Any]:
    outcome = {
        'status': status,
        'rounds': list(rounds),
        'round_count': len(rounds),
        'bundle_dir': str(bundle_dir) if bundle_dir else '',
        'final_repo': final_repo,
        'last_result': last_result,
        'error': error,
        'intervention': intervention,
    }
    if bundle_dir and status in TERMINAL_STATUSES:
        _write_json(bundle_dir / LOOP_RESULT_FILENAME, outcome)
    return outcome


def _sanitize_identifier(value: str) -> str:
    return ''.join(char if char.isalnum() or char in {'-', '_'} else '_' for char in value).strip('_') or 'report'


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
