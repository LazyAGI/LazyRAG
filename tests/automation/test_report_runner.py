from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from automation.opencode_adapter import execute_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _report_payload(repo: Path, fake_opencode: str) -> dict:
    return {
        'repo_path': str(repo),
        'base_ref': 'HEAD',
        'report_id': 'report_001',
        'instruction': 'Execute each task with minimal, verifiable changes.',
        'constraints': ['Only modify relevant files.'],
        'task_plans': [],
        'opencode': {
            'binary': fake_opencode,
        },
    }


def test_execute_report_orders_tasks_and_runs_validation(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt.')

    payload = _report_payload(temp_repo, fake_opencode)
    payload['task_plans'] = [
        {
            'task_id': 'T002',
            'module': 'retriever',
            'goal': 'second pass',
            'plan': ['validate cumulative change'],
            'risk': 2,
            'priority': 2,
            'depends_on': ['T001'],
            'change_targets': [{'file': 'target.txt'}],
            'validation': ['test "$(grep -c updated target.txt)" -eq 2'],
        },
        {
            'task_id': 'T001',
            'module': 'retriever',
            'goal': 'first pass',
            'plan': ['apply initial change'],
            'risk': 3,
            'priority': 1,
            'change_targets': [{'file': 'target.txt'}],
            'validation': ['grep -q updated target.txt'],
        },
    ]

    outcome = execute_report(payload)

    assert outcome['status'] == 'SUCCEEDED'
    assert [task_result['task_id'] for task_result in outcome['task_results']] == ['T001', 'T002']
    assert outcome['summary']['succeeded'] == 2
    assert outcome['summary']['files_changed'] == ['target.txt']
    assert outcome['task_results'][0]['validation_result']['status'] == 'PASSED'
    assert outcome['task_results'][1]['validation_result']['status'] == 'PASSED'


def test_execute_report_maps_change_targets_to_code_context_and_skips_validation(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt.')

    payload = _report_payload(temp_repo, fake_opencode)
    payload['task_plans'] = [
        {
            'task_id': 'T001',
            'module': 'retriever',
            'goal': 'map files',
            'plan': ['derive allowlist from change_targets'],
            'risk': 2,
            'priority': 1,
            'change_targets': [
                {'file': 'target.txt'},
                {'file': 'related.txt'},
            ],
        }
    ]

    outcome = execute_report(payload)

    task_result = outcome['task_results'][0]
    assert task_result['status'] == 'PARTIAL'
    assert task_result['validation_result']['status'] == 'SKIPPED'
    assert any('No executable validation commands were provided' in risk for risk in task_result['remaining_risks'])

    modify_result = task_result['modify_result']
    assert modify_result is not None
    task_input = json.loads((temp_repo / modify_result['artifacts_dir'] / 'input.json').read_text(encoding='utf-8'))
    assert task_input['code_context']['target_file'] == 'target.txt'
    assert task_input['code_context']['related_files'] == ['related.txt']


def test_execute_report_blocks_remaining_tasks_after_validation_failure(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt.')

    payload = _report_payload(temp_repo, fake_opencode)
    payload['task_plans'] = [
        {
            'task_id': 'T001',
            'module': 'retriever',
            'goal': 'fail validation',
            'plan': ['apply initial change'],
            'risk': 3,
            'priority': 1,
            'change_targets': [{'file': 'target.txt'}],
            'validation': ['grep -q missing target.txt'],
        },
        {
            'task_id': 'T002',
            'module': 'generator',
            'goal': 'should be blocked',
            'plan': ['run after dependency'],
            'risk': 1,
            'priority': 2,
            'depends_on': ['T001'],
            'change_targets': [{'file': 'target.txt'}],
        },
    ]

    outcome = execute_report(payload)

    assert outcome['status'] == 'FAILED'
    assert outcome['task_results'][0]['status'] == 'FAILED'
    assert outcome['task_results'][1]['status'] == 'BLOCKED'
    assert outcome['summary']['failed'] == 1
    assert outcome['summary']['blocked'] == 1


def test_execute_report_continues_unrelated_tasks_after_failure(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt.')

    payload = _report_payload(temp_repo, fake_opencode)
    payload['task_plans'] = [
        {
            'task_id': 'T001',
            'module': 'retriever',
            'goal': 'fail validation',
            'plan': ['apply initial change'],
            'risk': 3,
            'priority': 1,
            'change_targets': [{'file': 'target.txt'}],
            'validation': ['grep -q missing target.txt'],
        },
        {
            'task_id': 'T003',
            'module': 'query_rewriter',
            'goal': 'independent task should still run',
            'plan': ['apply independent change'],
            'risk': 1,
            'priority': 2,
            'change_targets': [{'file': 'target.txt'}],
            'validation': ['grep -q updated target.txt'],
        },
    ]

    outcome = execute_report(payload)

    assert outcome['status'] == 'PARTIAL'
    assert outcome['task_results'][0]['status'] == 'FAILED'
    assert outcome['task_results'][1]['status'] == 'SUCCEEDED'
    assert outcome['summary']['failed'] == 1
    assert outcome['summary']['succeeded'] == 1
    assert outcome['summary']['blocked'] == 0


def test_execute_report_skips_validation_for_no_change(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'no_change')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'No changes were necessary.')

    payload = _report_payload(temp_repo, fake_opencode)
    payload['task_plans'] = [
        {
            'task_id': 'T001',
            'module': 'retriever',
            'goal': 'no-op task',
            'plan': ['leave code unchanged'],
            'risk': 1,
            'priority': 1,
            'validation': ['grep -q updated target.txt'],
        }
    ]

    outcome = execute_report(payload)

    task_result = outcome['task_results'][0]
    assert outcome['status'] == 'SUCCEEDED'
    assert task_result['status'] == 'NO_CHANGE'
    assert task_result['validation_result']['status'] == 'SKIPPED'
    assert task_result['validation_result']['summary'] == 'Validation skipped because OpenCode made no code changes.'


def test_execute_report_returns_structured_failure_for_invalid_report(temp_repo: Path) -> None:
    outcome = execute_report({'repo_path': str(temp_repo)})

    assert outcome['status'] == 'FAILED'
    assert outcome['report_id'] == 'report'
    assert outcome['task_results'] == []
    assert any('report payload is required' in risk for risk in outcome['summary']['remaining_risks'])


def test_cli_routes_report_payload(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt.')

    payload = _report_payload(temp_repo, fake_opencode)
    payload['task_plans'] = [
        {
            'task_id': 'T001',
            'module': 'retriever',
            'goal': 'run through cli',
            'plan': ['apply initial change'],
            'risk': 1,
            'priority': 1,
            'change_targets': [{'file': 'target.txt'}],
            'validation': ['grep -q updated target.txt'],
        }
    ]

    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = (
        f'{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else str(PROJECT_ROOT)
    )

    result = subprocess.run(
        [sys.executable, '-m', 'automation.opencode_adapter.cli'],
        input=json.dumps(payload),
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
    assert rendered['task_results'][0]['task_id'] == 'T001'
