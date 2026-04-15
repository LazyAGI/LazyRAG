from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from automation.opencode_adapter import execute


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _payload(repo: Path, fake_opencode: str) -> dict:
    return {
        'repo_path': str(repo),
        'base_ref': 'HEAD',
        'task_plan': {
            'task_id': 'T001',
            'goal': 'update target',
            'plan': ['change target'],
        },
        'code_context': {
            'target_file': 'target.txt',
            'related_files': ['related.txt'],
            'current_logic': 'base file',
        },
        'opencode': {
            'binary': fake_opencode,
        },
    }


def _payload_without_code_context(repo: Path, fake_opencode: str) -> dict:
    payload = _payload(repo, fake_opencode)
    payload.pop('code_context')
    return payload


def test_execute_success_generates_diff(temp_repo: Path, fake_opencode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt.')

    outcome = execute(_payload(temp_repo, fake_opencode))

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['error'] is None
    assert outcome['result'] is not None
    assert outcome['result']['files_changed'] == ['target.txt']
    assert 'updated' in outcome['result']['diff']
    assert outcome['result']['change_summary'] == 'Updated target.txt.'
    artifacts_dir = temp_repo / outcome['artifacts_dir']
    assert (artifacts_dir / 'input.json').exists()
    assert (artifacts_dir / 'prompt.txt').exists()
    assert (artifacts_dir / 'events.jsonl').exists()
    assert (artifacts_dir / 'diff.patch').exists()
    events_content = (artifacts_dir / 'events.jsonl').read_text(encoding='utf-8')
    assert events_content.endswith('\n')
    assert len([line for line in events_content.splitlines() if line.strip()]) >= 1
    result_json = json.loads((artifacts_dir / 'result.json').read_text(encoding='utf-8'))
    assert result_json['status'] == 'SUCCEEDED'


def test_execute_no_change(temp_repo: Path, fake_opencode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'no_change')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'No changes were necessary.')

    outcome = execute(_payload(temp_repo, fake_opencode))

    assert outcome['status'] == 'NO_CHANGE'
    assert outcome['error'] is None
    assert outcome['result'] == {
        'diff': '',
        'files_changed': [],
        'change_summary': 'No changes were necessary.',
    }


def test_execute_allows_missing_code_context(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated target.txt without extra context.')

    outcome = execute(_payload_without_code_context(temp_repo, fake_opencode))

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['error'] is None
    assert outcome['result'] is not None
    assert outcome['result']['files_changed'] == ['target.txt']
    assert outcome['result']['change_summary'] == 'Updated target.txt without extra context.'


def test_execute_scope_violation(temp_repo: Path, fake_opencode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'scope_violation')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    monkeypatch.setenv('FAKE_OPENCODE_OUTSIDE', 'outside.txt')

    outcome = execute(_payload(temp_repo, fake_opencode))

    assert outcome['status'] == 'FAILED'
    assert outcome['error'] is not None
    assert outcome['error']['code'] == 'SCOPE_VIOLATION'
    assert outcome['error']['details']['violations'] == ['outside.txt']


def test_execute_auth_missing(temp_repo: Path, fake_opencode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_AUTH_COUNT', '0')

    outcome = execute(_payload(temp_repo, fake_opencode))

    assert outcome['status'] == 'FAILED'
    assert outcome['error'] is not None
    assert outcome['error']['code'] == 'OPENCODE_AUTH_MISSING'


def test_execute_maps_opencode_failure(temp_repo: Path, fake_opencode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'exec_error')

    outcome = execute(_payload(temp_repo, fake_opencode))

    assert outcome['status'] == 'FAILED'
    assert outcome['error'] is not None
    assert outcome['error']['code'] == 'OPENCODE_EXEC_FAILED'


def test_cli_reads_stdin_and_writes_stdout(
    temp_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', 'target.txt')
    payload = _payload(temp_repo, fake_opencode)
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
    assert rendered['result']['files_changed'] == ['target.txt']


def test_cli_invalid_payload_returns_json_error() -> None:
    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = (
        f'{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else str(PROJECT_ROOT)
    )

    result = subprocess.run(
        [sys.executable, '-m', 'automation.opencode_adapter.cli'],
        input=json.dumps({'repo_path': '/tmp/repo'}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=str(PROJECT_ROOT),
        env=env,
    )

    assert result.returncode == 1
    rendered = json.loads(result.stdout)
    assert rendered['status'] == 'FAILED'
    assert rendered['error']['code'] == 'OPENCODE_EXEC_FAILED'
    assert 'payload must contain task_plan or report/task_plans' in rendered['error']['message']
