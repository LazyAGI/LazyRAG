from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import automation.opencode_adapter.loop_runner as loop_runner
from automation.opencode_adapter.intervention import (
    HANDOFF_JSON_FILENAME,
    HANDOFF_MARKDOWN_FILENAME,
)
from automation.opencode_adapter.loop_runner import META_FILENAME, run_report_fix_loop


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FILE = 'algorithm/chat/pipelines/builders/get_retriever.py'


@pytest.fixture
def temp_algorithm_repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'algorithm_repo'
    repo.mkdir()
    (repo / ALLOWED_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / ALLOWED_FILE).write_text('base\n', encoding='utf-8')
    (repo / 'tests').mkdir()
    return repo


def _report_payload(fake_opencode: str) -> dict:
    return {
        'report_id': 'report_loop_runner',
        'summary': {
            'top_issue': 'improve retrieval behavior with minimal changes',
        },
        'modification_plan': [
            {
                'stage': 'retrieve',
                'priority': 1,
                'hypothesis': 'improve retrieval recall',
                'files': [ALLOWED_FILE],
                'suggested_changes': [{'file': ALLOWED_FILE, 'param': 'topk'}],
            }
        ],
        'opencode': {
            'binary': fake_opencode,
        },
    }


def _write_report(tmp_path: Path, fake_opencode: str) -> Path:
    report_path = tmp_path / 'report.json'
    report_path.write_text(
        json.dumps(_report_payload(fake_opencode), ensure_ascii=False),
        encoding='utf-8',
    )
    return report_path


def _write_count_check_script(
    tmp_path: Path,
    *,
    expected_count: int | None = None,
    minimum_count: int | None = None,
    always_fail: bool = False,
    name: str = 'check_repo.py',
) -> Path:
    script_path = tmp_path / name
    lines = [
        'from pathlib import Path',
        f'path = Path.cwd() / {ALLOWED_FILE!r}',
        "content = path.read_text(encoding='utf-8')",
        "count = content.count('updated')",
    ]

    if always_fail:
        lines.extend(
            [
                "print(f'AssertionError: forced failure with count={count}')",
                "print('=== 1 failed in 0.01s ===')",
                'raise SystemExit(1)',
            ]
        )
    elif expected_count is not None:
        lines.extend(
            [
                f'if count == {expected_count}:',
                "    print('=== 1 passed in 0.01s ===')",
                '    raise SystemExit(0)',
                f"print(f'AssertionError: expected {expected_count} updated markers but got {{count}}')",
                "print('=== 1 failed in 0.01s ===')",
                'raise SystemExit(1)',
            ]
        )
    elif minimum_count is not None:
        lines.extend(
            [
                f'if count >= {minimum_count}:',
                "    print('=== 1 passed in 0.01s ===')",
                '    raise SystemExit(0)',
                f"print(f'AssertionError: expected at least {minimum_count} updated markers but got {{count}}')",
                "print('=== 1 failed in 0.01s ===')",
                'raise SystemExit(1)',
            ]
        )
    else:
        raise AssertionError('either expected_count, minimum_count, or always_fail must be set')

    script_path.write_text('\n'.join(lines), encoding='utf-8')
    return script_path


def _single_bundle_dir(artifact_root: Path) -> Path:
    candidates = [path for path in artifact_root.iterdir() if path.is_dir()]
    assert len(candidates) == 1
    return candidates[0]


def _load_meta(bundle_dir: Path) -> dict:
    return json.loads((bundle_dir / META_FILENAME).read_text(encoding='utf-8'))


def test_run_report_fix_loop_retries_with_full_test_log(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'modify_after_test_failure')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv(
        'FAKE_OPENCODE_SUMMARY',
        'Fixed the failing test based on the full log.',
    )

    report_path = _write_report(tmp_path, fake_opencode)
    check_script = _write_count_check_script(tmp_path, minimum_count=1)

    outcome = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=2,
        test_command=[sys.executable, str(check_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['round_count'] == 2
    assert outcome['last_result']['files_changed'] == [ALLOWED_FILE]
    assert outcome['last_result']['change_summary'] == 'Fixed the failing test based on the full log.'
    assert ALLOWED_FILE in outcome['last_result']['diffs']

    bundle_dir = Path(outcome['bundle_dir'])
    assert bundle_dir.exists()
    assert (bundle_dir / 'baseline_repo').is_dir()
    assert (bundle_dir / 'source.report.json').is_file()
    round_1_test_log = Path(outcome['rounds'][0]['test_log_path'])
    assert 'expected at least 1 updated markers but got 0' in round_1_test_log.read_text(
        encoding='utf-8'
    )
    assert 'TEST FAILURE LOG:' in (
        bundle_dir / 'round_2' / 'instruction.txt'
    ).read_text(encoding='utf-8')

    final_repo = Path(outcome['final_repo'])
    assert final_repo.is_dir()
    assert (
        final_repo / 'algorithm/evo/output/reports/source.report.json'
    ).is_file()
    assert (final_repo / 'algorithm/evo/output/val/test.log').is_file()
    assert 'updated' in (final_repo / ALLOWED_FILE).read_text(
        encoding='utf-8'
    )


def test_run_report_fix_loop_resumes_from_cli_running_checkpoint(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    check_script = _write_count_check_script(tmp_path, minimum_count=1)
    artifact_root = tmp_path / 'loop_artifacts'

    original_run_cli_once = loop_runner._run_cli_once
    state = {'raised': False}

    def interrupt_once(**kwargs):
        if not state['raised']:
            state['raised'] = True
            raise KeyboardInterrupt('interrupt after checkpointed cli_running state')
        return original_run_cli_once(**kwargs)

    monkeypatch.setattr(loop_runner, '_run_cli_once', interrupt_once)

    with pytest.raises(KeyboardInterrupt):
        run_report_fix_loop(
            str(report_path),
            str(temp_algorithm_repo),
            max_rounds=2,
            test_command=[sys.executable, str(check_script)],
            artifact_root=str(artifact_root),
        )

    bundle_dir = _single_bundle_dir(artifact_root)
    meta = _load_meta(bundle_dir)
    assert meta['active_stage'] == 'cli_running'
    assert meta['active_round'] == 1

    outcome = run_report_fix_loop(
        resume_bundle=str(bundle_dir),
        max_rounds=2,
        test_command=[sys.executable, str(check_script)],
    )

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['round_count'] == 1
    assert Path(outcome['final_repo']).is_dir()


def test_run_report_fix_loop_resumes_from_test_running_checkpoint(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    check_script = _write_count_check_script(tmp_path, minimum_count=1)
    artifact_root = tmp_path / 'loop_artifacts'

    original_run_tests_once = loop_runner._run_tests_once
    state = {'raised': False}

    def interrupt_once(**kwargs):
        if not state['raised']:
            state['raised'] = True
            raise KeyboardInterrupt('interrupt after checkpointed test_running state')
        return original_run_tests_once(**kwargs)

    monkeypatch.setattr(loop_runner, '_run_tests_once', interrupt_once)

    with pytest.raises(KeyboardInterrupt):
        run_report_fix_loop(
            str(report_path),
            str(temp_algorithm_repo),
            max_rounds=2,
            test_command=[sys.executable, str(check_script)],
            artifact_root=str(artifact_root),
        )

    bundle_dir = _single_bundle_dir(artifact_root)
    cli_run_count = len(list((bundle_dir / 'cli_runs').iterdir()))
    meta = _load_meta(bundle_dir)
    assert meta['active_stage'] == 'test_running'
    assert meta['active_round'] == 1

    outcome = run_report_fix_loop(
        resume_bundle=str(bundle_dir),
        max_rounds=2,
        test_command=[sys.executable, str(check_script)],
    )

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['round_count'] == 1
    assert len(list((bundle_dir / 'cli_runs').iterdir())) == cli_run_count


def test_run_report_fix_loop_generates_handoff_after_max_rounds(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    check_script = _write_count_check_script(tmp_path, always_fail=True)

    outcome = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=3,
        test_command=[sys.executable, str(check_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )

    assert outcome['status'] == 'INTERVENTION_REQUIRED'
    assert outcome['round_count'] == 3
    assert outcome['intervention']['reason'] == 'MAX_ROUNDS_EXCEEDED'

    bundle_dir = Path(outcome['bundle_dir'])
    handoff_json = bundle_dir / HANDOFF_JSON_FILENAME
    handoff_md = bundle_dir / HANDOFF_MARKDOWN_FILENAME
    assert handoff_json.is_file()
    assert handoff_md.is_file()

    handoff = json.loads(handoff_json.read_text(encoding='utf-8'))
    assert handoff['total_rounds'] == 3
    assert len(handoff['attempts']) == 3
    assert handoff['attempts'][-1]['changed_files'] == [ALLOWED_FILE]
    assert 'Current repo copy:' in handoff['user_prompt_draft']
    assert 'OpenCode Loop Handoff' in handoff_md.read_text(encoding='utf-8')


def test_run_report_fix_loop_resume_mode_continue_uses_latest_repo_copy(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    fail_script = _write_count_check_script(tmp_path, always_fail=True, name='always_fail.py')
    first_outcome = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=3,
        test_command=[sys.executable, str(fail_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )

    assert first_outcome['status'] == 'INTERVENTION_REQUIRED'

    continue_script = _write_count_check_script(tmp_path, expected_count=4, name='continue_check.py')
    resumed = run_report_fix_loop(
        resume_bundle=first_outcome['bundle_dir'],
        resume_mode='continue',
        max_rounds=1,
        test_command=[sys.executable, str(continue_script)],
    )

    assert resumed['status'] == 'SUCCEEDED'
    assert resumed['round_count'] == 4
    assert (Path(resumed['final_repo']) / ALLOWED_FILE).read_text(encoding='utf-8').count('updated') == 4


def test_run_report_fix_loop_resume_mode_rollback_uses_baseline_repo_copy(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    fail_script = _write_count_check_script(tmp_path, always_fail=True, name='always_fail.py')
    first_outcome = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=3,
        test_command=[sys.executable, str(fail_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )

    assert first_outcome['status'] == 'INTERVENTION_REQUIRED'

    rollback_script = _write_count_check_script(tmp_path, expected_count=1, name='rollback_check.py')
    resumed = run_report_fix_loop(
        resume_bundle=first_outcome['bundle_dir'],
        resume_mode='rollback',
        max_rounds=1,
        test_command=[sys.executable, str(rollback_script)],
    )

    assert resumed['status'] == 'SUCCEEDED'
    assert resumed['round_count'] == 4
    assert (Path(resumed['final_repo']) / ALLOWED_FILE).read_text(encoding='utf-8').count('updated') == 1


def test_run_report_fix_loop_resume_injects_extra_instruction(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    fail_script = _write_count_check_script(tmp_path, always_fail=True, name='always_fail.py')
    first_outcome = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=1,
        test_command=[sys.executable, str(fail_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )

    assert first_outcome['status'] == 'INTERVENTION_REQUIRED'

    extra_instruction = 'Prefer a smaller, strictly scoped retrieval tweak.'
    success_script = _write_count_check_script(tmp_path, expected_count=2, name='resume_success.py')
    resumed = run_report_fix_loop(
        resume_bundle=first_outcome['bundle_dir'],
        resume_mode='continue',
        max_rounds=1,
        test_command=[sys.executable, str(success_script)],
        extra_instruction=extra_instruction,
    )

    assert resumed['status'] == 'SUCCEEDED'
    instruction = (
        Path(resumed['bundle_dir']) / 'round_2' / 'instruction.txt'
    ).read_text(encoding='utf-8')
    assert extra_instruction in instruction


def test_cli_loop_mode_defaults_to_run_all_script(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'modify_after_test_failure')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv(
        'FAKE_OPENCODE_SUMMARY',
        'Fixed the failing test based on the full log.',
    )

    report_path = _write_report(tmp_path, fake_opencode)

    run_all_path = temp_algorithm_repo / 'tests' / 'run-all.sh'
    run_all_path.write_text(
        '\n'.join(
            [
                '#!/usr/bin/env bash',
                'set -e',
                f'TARGET="{ALLOWED_FILE}"',
                'if grep -q "updated" "$TARGET"; then',
                '  echo "=== 1 passed in 0.01s ==="',
                '  exit 0',
                'fi',
                'echo "AssertionError: missing updated marker in retriever file"',
                'echo "=== 1 failed in 0.01s ==="',
                'exit 1',
            ]
        ),
        encoding='utf-8',
    )

    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = (
        f'{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}'
        if existing_pythonpath
        else str(PROJECT_ROOT)
    )

    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'automation.opencode_adapter.cli',
            '--loop',
            str(report_path),
            '--repo',
            str(temp_algorithm_repo),
            '--max-rounds',
            '2',
            '--artifact-root',
            str(tmp_path / 'loop_artifacts'),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=str(PROJECT_ROOT),
        env=env,
    )

    assert result.returncode == 0
    rendered = json.loads(result.stdout)
    assert rendered['status'] == 'SUCCEEDED'
    assert rendered['round_count'] == 2
    assert rendered['last_result']['files_changed'] == [ALLOWED_FILE]
    assert rendered['last_result']['change_summary'] == 'Fixed the failing test based on the full log.'
    assert ALLOWED_FILE in rendered['last_result']['diffs']
    test_result = json.loads(
        (Path(rendered['bundle_dir']) / 'round_1' / 'test.result.json').read_text(encoding='utf-8')
    )
    assert test_result['command'] == ['bash', 'tests/run-all.sh']


def test_cli_loop_resume_bundle_supports_resume_mode_and_extra_instruction(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = _write_report(tmp_path, fake_opencode)
    fail_script = _write_count_check_script(tmp_path, always_fail=True, name='always_fail.py')
    initial = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=1,
        test_command=[sys.executable, str(fail_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )
    assert initial['status'] == 'INTERVENTION_REQUIRED'

    resume_script = _write_count_check_script(tmp_path, expected_count=1, name='cli_resume.py')
    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = (
        f'{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}'
        if existing_pythonpath
        else str(PROJECT_ROOT)
    )

    extra_instruction = 'Retry from the clean baseline with a smaller edit.'
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'automation.opencode_adapter.cli',
            '--loop',
            '--resume-bundle',
            initial['bundle_dir'],
            '--resume-mode',
            'rollback',
            '--max-rounds',
            '1',
            '--extra-instruction',
            extra_instruction,
            '--test-command',
            f'{sys.executable} {resume_script}',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=str(PROJECT_ROOT),
        env=env,
    )

    assert result.returncode == 0
    rendered = json.loads(result.stdout)
    assert rendered['status'] == 'SUCCEEDED'
    assert rendered['round_count'] == 2
    instruction = (Path(rendered['bundle_dir']) / 'round_2' / 'instruction.txt').read_text(encoding='utf-8')
    assert extra_instruction in instruction
