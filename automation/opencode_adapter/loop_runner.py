from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Dict, List

from algorithm.evo.output.test_log_collector import check_pytest_log_passed
from automation.opencode_adapter.errors import AdapterError, OPENCODE_EXEC_FAILED, REPO_PATH_INVALID


LOOP_CLI_FAILED = 'LOOP_CLI_FAILED'
LOOP_ARTIFACT_MISSING = 'LOOP_ARTIFACT_MISSING'
MAX_ROUNDS_EXCEEDED = 'MAX_ROUNDS_EXCEEDED'
REPORT_JSON_INVALID = 'REPORT_JSON_INVALID'
DEFAULT_MAX_ROUNDS = 3
DEFAULT_TESTS_PATH = 'tests'
DEFAULT_LOOP_ARTIFACT_ROOT = Path(tempfile.gettempdir()) / 'lazy-rag-loop'
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path('algorithm/evo/output')
OUTPUT_REPORTS_DIR = OUTPUT_ROOT / 'reports'
OUTPUT_VAL_DIR = OUTPUT_ROOT / 'val'


def run_report_fix_loop(
    report_json_path: str,
    repo_path: str,
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    tests_path: str = DEFAULT_TESTS_PATH,
    test_command: Sequence[str] | None = None,
    artifact_root: str | None = None,
    python_executable: str | None = None,
) -> Dict[str, Any]:
    bundle_dir = ''
    try:
        report_path = _validate_report_json_path(report_json_path)
        repo_root = _validate_repo_path(repo_path)
        report = _load_report(report_path)
        report_id = str(report.get('report_id') or report_path.stem or 'report').strip() or 'report'

        artifact_base = Path(artifact_root).expanduser() if artifact_root else DEFAULT_LOOP_ARTIFACT_ROOT
        artifact_base.mkdir(parents=True, exist_ok=True)
        bundle_root = Path(
            tempfile.mkdtemp(prefix=f'{_sanitize_identifier(report_id)}_', dir=str(artifact_base.resolve()))
        ).resolve()
        bundle_dir = str(bundle_root)

        current_repo = str(repo_root)
        cli_artifact_root = bundle_root / 'cli_runs'
        rounds: List[Dict[str, Any]] = []
        previous_cli_result: Dict[str, Any] | None = None
        previous_test_log = ''
        python_bin = python_executable or sys.executable

        for round_index in range(1, max_rounds + 1):
            round_dir = bundle_root / f'round_{round_index}'
            round_dir.mkdir(parents=True, exist_ok=True)

            instruction = _build_round_instruction(
                round_index=round_index,
                previous_cli_result=previous_cli_result,
                previous_test_log=previous_test_log,
            )
            _write_text(round_dir / 'instruction.txt', instruction)

            cli_result = _run_cli_once(
                report_json_path=report_path,
                repo_path=Path(current_repo),
                instruction=instruction,
                artifact_root=cli_artifact_root,
                python_executable=python_bin,
            )
            _write_text(round_dir / 'cli.stdout.json', cli_result['stdout'])
            _write_text(round_dir / 'cli.stderr.log', cli_result['stderr'])
            _write_json(round_dir / 'cli.result.json', cli_result['payload'])

            round_state: Dict[str, Any] = {
                'round': round_index,
                'instruction_path': str(round_dir / 'instruction.txt'),
                'cli_result_path': str(round_dir / 'cli.result.json'),
                'cli_artifacts_dir': str(cli_result['payload'].get('artifacts_dir') or ''),
                'status': cli_result['payload'].get('status'),
            }

            if cli_result['payload'].get('status') == 'FAILED':
                round_state['error'] = cli_result['payload'].get('error')
                rounds.append(round_state)
                return _build_loop_outcome(
                    status='FAILED',
                    bundle_dir=bundle_root,
                    rounds=rounds,
                    last_result=cli_result['payload'].get('result'),
                    error={
                        'code': LOOP_CLI_FAILED,
                        'message': 'cli execution failed inside the fix loop',
                        'details': {'round': round_index, 'cli_error': cli_result['payload'].get('error')},
                    },
                )

            repo_copy = Path(str(cli_result['payload'].get('artifacts_dir') or '')).resolve() / 'repo_copy'
            if not repo_copy.is_dir():
                round_state['error'] = {'code': LOOP_ARTIFACT_MISSING, 'message': 'repo_copy was not found'}
                rounds.append(round_state)
                return _build_loop_outcome(
                    status='FAILED',
                    bundle_dir=bundle_root,
                    rounds=rounds,
                    last_result=cli_result['payload'].get('result'),
                    error={
                        'code': LOOP_ARTIFACT_MISSING,
                        'message': 'repo_copy was not found after cli execution',
                        'details': {'round': round_index, 'artifacts_dir': cli_result['payload'].get('artifacts_dir')},
                    },
                )

            repo_reports_dir, repo_val_dir = _ensure_output_dirs(repo_copy)
            report_copy_path = repo_reports_dir / 'source.report.json'
            shutil.copy2(report_path, report_copy_path)
            round_state['report_copy_path'] = str(report_copy_path)

            test_result = _run_tests_once(
                repo_copy=repo_copy,
                output_val_dir=repo_val_dir,
                tests_path=tests_path,
                test_command=test_command,
                python_executable=python_bin,
            )
            _write_json(round_dir / 'test.result.json', test_result)

            round_state['test_result_path'] = str(round_dir / 'test.result.json')
            round_state['test_log_path'] = test_result['log_path']
            round_state['test_status'] = test_result['status']
            rounds.append(round_state)

            if test_result['status'] == 'PASSED':
                return _build_loop_outcome(
                    status='SUCCEEDED',
                    bundle_dir=bundle_root,
                    rounds=rounds,
                    last_result=cli_result['payload'].get('result'),
                    final_repo=repo_copy,
                    error=None,
                )

            previous_cli_result = cli_result['payload']
            previous_test_log = test_result['log']
            current_repo = str(repo_copy)

        return _build_loop_outcome(
            status='FAILED',
            bundle_dir=bundle_root,
            rounds=rounds,
            last_result=previous_cli_result.get('result') if previous_cli_result else None,
            error={
                'code': MAX_ROUNDS_EXCEEDED,
                'message': 'test loop did not pass within the maximum number of rounds',
                'details': {'max_rounds': max_rounds},
            },
        )
    except AdapterError as exc:
        return _build_loop_outcome(
            status='FAILED',
            bundle_dir=Path(bundle_dir) if bundle_dir else None,
            rounds=[],
            last_result=None,
            error=exc.to_payload(),
        )
    except Exception as exc:
        wrapped = AdapterError(OPENCODE_EXEC_FAILED, 'unexpected loop runner failure', {'error': str(exc)})
        return _build_loop_outcome(
            status='FAILED',
            bundle_dir=Path(bundle_dir) if bundle_dir else None,
            rounds=[],
            last_result=None,
            error=wrapped.to_payload(),
        )


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


def _build_round_instruction(
    *,
    round_index: int,
    previous_cli_result: Dict[str, Any] | None,
    previous_test_log: str,
) -> str:
    if round_index == 1:
        return textwrap.dedent(
            """
            根据 report 做一次最小修改。
            只修改 allowlist 范围内的必要文件。
            不要做无关重构，不要扩大改动范围。
            """
        ).strip()

    previous_result = json.dumps(previous_cli_result or {}, ensure_ascii=False, indent=2, sort_keys=True)
    return textwrap.dedent(
        f"""
        根据上一轮测试失败日志继续修复。
        只修复日志暴露的问题，不要扩大改动范围，不要修改 allowlist 之外的文件。

        上一轮 CLI 结果:
        {previous_result}

        TEST FAILURE LOG:
        {previous_test_log}
        """
    ).strip()


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
    tests_path: str,
    test_command: Sequence[str] | None,
    python_executable: str,
) -> Dict[str, Any]:
    command = list(test_command) if test_command else [python_executable, '-m', 'pytest', tests_path]
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
        'status': 'PASSED' if passed else 'FAILED',
        'returncode': result.returncode,
        'command': command,
        'log': log,
        'log_path': str(log_path),
    }


def _ensure_output_dirs(repo_copy: Path) -> tuple[Path, Path]:
    reports_dir = repo_copy / OUTPUT_REPORTS_DIR
    val_dir = repo_copy / OUTPUT_VAL_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir, val_dir


def _build_loop_outcome(
    *,
    status: str,
    bundle_dir: Path | None,
    rounds: Sequence[Dict[str, Any]],
    last_result: Dict[str, Any] | None,
    error: Dict[str, Any] | None,
    final_repo: Path | None = None,
) -> Dict[str, Any]:
    outcome = {
        'status': status,
        'rounds': list(rounds),
        'round_count': len(rounds),
        'bundle_dir': str(bundle_dir) if bundle_dir else '',
        'final_repo': str(final_repo) if final_repo else '',
        'last_result': last_result,
        'error': error,
    }
    if bundle_dir:
        _write_json(bundle_dir / 'loop.result.json', outcome)
    return outcome


def _sanitize_identifier(value: str) -> str:
    return ''.join(char if char.isalnum() or char in {'-', '_'} else '_' for char in value).strip('_') or 'report'


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
