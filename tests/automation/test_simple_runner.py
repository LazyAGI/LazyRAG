from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from automation.opencode_adapter.simple_runner import execute_simple_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FILE = 'algorithm/chat/pipelines/builders/get_retriever.py'
SECOND_ALLOWED_FILE = 'algorithm/chat/components/tmp/local_models.py'


@pytest.fixture
def temp_algorithm_repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'algorithm_repo'
    repo.mkdir()
    (repo / ALLOWED_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / ALLOWED_FILE).write_text('base\n', encoding='utf-8')
    (repo / SECOND_ALLOWED_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / SECOND_ALLOWED_FILE).write_text(
        'class BgeM3Embed:\n    pass\n',
        encoding='utf-8',
    )
    return repo


def _report_payload(fake_opencode: str, modification_plan: list[dict]) -> dict:
    return {
        'report_id': 'report_simple_runner',
        'summary': {
            'top_issue': 'improve retrieval behavior with minimal changes',
        },
        'modification_plan': modification_plan,
        'opencode': {
            'binary': fake_opencode,
        },
    }


def test_execute_simple_report_success(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    payload = _report_payload(
        fake_opencode,
        [
            {
                'task_id': 'T001',
                'stage': 'retrieve',
                'priority': 1,
                'hypothesis': 'improve retrieval recall',
                'files': [ALLOWED_FILE],
                'suggested_changes': [{'file': ALLOWED_FILE, 'param': 'topk'}],
            }
        ],
    )

    outcome = execute_simple_report(
        payload,
        repo_path=str(temp_algorithm_repo),
        instruction='完成这个json内的任务',
        artifact_root=str(tmp_path / 'artifacts'),
    )

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['error'] is None
    assert outcome['result']['files_changed'] == [ALLOWED_FILE]
    assert outcome['result']['change_summary'] == 'Updated retriever settings.'
    assert ALLOWED_FILE in outcome['result']['diffs']
    diff = outcome['result']['diffs'][ALLOWED_FILE]
    assert diff['old'] == 'base\n'
    assert diff['new'] == 'base\n\nupdated\n'
    assert 'updated' in diff['unified']
    assert Path(outcome['artifacts_dir']).exists()


def test_execute_simple_report_rejects_forbidden_change_target(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)

    payload = _report_payload(
        fake_opencode,
        [
            {
                'task_id': 'T001',
                'stage': 'retrieve',
                'priority': 1,
                'hypothesis': 'attempt forbidden edit',
                'files': ['algorithm/chat/utils/load_config.py'],
                'suggested_changes': [
                    {'file': 'algorithm/chat/utils/load_config.py', 'param': 'topk'}
                ],
            }
        ],
    )

    outcome = execute_simple_report(
        payload,
        repo_path=str(temp_algorithm_repo),
        instruction='完成这个json内的任务',
        artifact_root=str(tmp_path / 'artifacts'),
    )

    assert outcome['status'] == 'FAILED'
    assert outcome['result'] is None
    assert outcome['error']['code'] == 'TASK_SCOPE_FORBIDDEN'


def test_execute_simple_report_rejects_scope_violation(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'scope_violation')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv(
        'FAKE_OPENCODE_OUTSIDE',
        'algorithm/chat/prompts/rewrite.py',
    )

    payload = _report_payload(
        fake_opencode,
        [
            {
                'task_id': 'T001',
                'stage': 'retrieve',
                'priority': 1,
                'hypothesis': 'modify only allowed file',
                'files': [ALLOWED_FILE],
                'suggested_changes': [{'file': ALLOWED_FILE, 'param': 'topk'}],
            }
        ],
    )

    outcome = execute_simple_report(
        payload,
        repo_path=str(temp_algorithm_repo),
        instruction='完成这个json内的任务',
        artifact_root=str(tmp_path / 'artifacts'),
    )

    assert outcome['status'] == 'FAILED'
    assert outcome['result'] is None
    assert outcome['error']['code'] == 'SCOPE_VIOLATION'
    assert outcome['error']['details']['violations'] == [
        'algorithm/chat/prompts/rewrite.py'
    ]


def test_execute_simple_report_returns_no_change(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'no_change')
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'No change needed.')

    payload = _report_payload(
        fake_opencode,
        [
            {
                'task_id': 'T001',
                'stage': 'retrieve',
                'priority': 1,
                'hypothesis': 'no changes required',
                'files': [ALLOWED_FILE],
                'suggested_changes': [{'file': ALLOWED_FILE, 'param': 'topk'}],
            }
        ],
    )

    outcome = execute_simple_report(
        payload,
        repo_path=str(temp_algorithm_repo),
        instruction='完成这个json内的任务',
        artifact_root=str(tmp_path / 'artifacts'),
    )

    assert outcome['status'] == 'NO_CHANGE'
    assert outcome['result']['files_changed'] == []
    assert outcome['result']['change_summary'] == 'No change needed.'
    assert outcome['result']['diffs'] == {}


def test_simple_runner_cli_reads_report_json(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = tmp_path / 'report.json'
    report_path.write_text(
        json.dumps(
            _report_payload(
                fake_opencode,
                [
                    {
                        'task_id': 'T001',
                        'stage': 'retrieve',
                        'priority': 1,
                        'hypothesis': 'cli run',
                        'files': [ALLOWED_FILE],
                        'suggested_changes': [{'file': ALLOWED_FILE, 'param': 'topk'}],
                    }
                ],
            ),
            ensure_ascii=False,
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
            str(report_path),
            '--artifact-root',
            str(tmp_path / 'artifacts'),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=str(temp_algorithm_repo),
        env=env,
    )

    assert result.returncode == 0
    rendered = json.loads(result.stdout)
    assert rendered['status'] == 'SUCCEEDED'
    assert rendered['result']['files_changed'] == [ALLOWED_FILE]


def test_simple_runner_cli_reads_report_json_from_natural_language(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'success_modify')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_SUMMARY', 'Updated retriever settings.')

    report_path = tmp_path / 'report.json'
    report_path.write_text(
        json.dumps(
            _report_payload(
                fake_opencode,
                [
                    {
                        'task_id': 'T001',
                        'stage': 'retrieve',
                        'priority': 1,
                        'hypothesis': 'cli natural language run',
                        'files': [ALLOWED_FILE],
                        'suggested_changes': [{'file': ALLOWED_FILE, 'param': 'topk'}],
                    }
                ],
            ),
            ensure_ascii=False,
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
            f'根据{report_path}进行修改',
            '--artifact-root',
            str(tmp_path / 'artifacts'),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=str(temp_algorithm_repo),
        env=env,
    )

    assert result.returncode == 0
    rendered = json.loads(result.stdout)
    assert rendered['status'] == 'SUCCEEDED'
    assert rendered['result']['files_changed'] == [ALLOWED_FILE]
