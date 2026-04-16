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


def _init_repo(path: Path) -> None:
    subprocess.run(
        ['git', 'init'],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        ['git', 'config', 'user.email', 'tests@example.com'],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        ['git', 'config', 'user.name', 'Automation Tests'],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def temp_algorithm_repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'algorithm_repo'
    repo.mkdir()
    _init_repo(repo)
    (repo / ALLOWED_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / ALLOWED_FILE).write_text('base\n', encoding='utf-8')
    (repo / SECOND_ALLOWED_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / SECOND_ALLOWED_FILE).write_text('class BgeM3Embed:\n    pass\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(
        ['git', 'commit', '-m', 'init'],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return repo


def _report_payload(fake_opencode: str, task_plans: list[dict]) -> dict:
    return {
        'report_id': 'report_simple_runner',
        'instruction': '请按 task_plans 逐项执行最小可验证改动。',
        'constraints': ['Only modify files from change_targets.'],
        'task_plans': task_plans,
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
                'module': 'retriever',
                'goal': 'improve retrieval recall',
                'plan': ['tune retriever'],
                'change_targets': [{'file': ALLOWED_FILE}],
                'validation': [f'grep -q updated {ALLOWED_FILE}'],
            }
        ],
    )

    outcome = execute_simple_report(
        payload,
        repo_path=str(temp_algorithm_repo),
        instruction='完成这个json内的任务',
        max_rounds=2,
        artifact_root=str(tmp_path / 'artifacts'),
    )

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['error'] is None
    task_result = outcome['task_results'][0]
    assert task_result['status'] == 'SUCCEEDED'
    assert task_result['result'] == {
        'diff': task_result['result']['diff'],
        'files_changed': [ALLOWED_FILE],
        'change_summary': 'Updated retriever settings.',
    }
    assert 'updated' in task_result['result']['diff']
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
                'module': 'retriever',
                'goal': 'attempt forbidden edit',
                'plan': ['do not allow this'],
                'change_targets': [{'file': 'algorithm/chat/utils/load_config.py'}],
                'validation': [f'grep -q updated {ALLOWED_FILE}'],
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
    task_result = outcome['task_results'][0]
    assert task_result['status'] == 'FAILED'
    assert task_result['result'] is None
    assert task_result['error']['code'] == 'TASK_SCOPE_FORBIDDEN'


def test_execute_simple_report_rejects_scope_violation(
    temp_algorithm_repo: Path,
    fake_opencode: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('FAKE_OPENCODE_MODE', 'scope_violation')
    monkeypatch.setenv('FAKE_OPENCODE_TARGET', ALLOWED_FILE)
    monkeypatch.setenv('FAKE_OPENCODE_OUTSIDE', 'algorithm/chat/prompts/rewrite.py')

    payload = _report_payload(
        fake_opencode,
        [
            {
                'task_id': 'T001',
                'module': 'retriever',
                'goal': 'modify only allowed file',
                'plan': ['should fail on scope violation'],
                'change_targets': [{'file': ALLOWED_FILE}],
                'validation': [f'grep -q updated {ALLOWED_FILE}'],
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
    task_result = outcome['task_results'][0]
    assert task_result['status'] == 'FAILED'
    assert task_result['result'] is None
    assert task_result['error']['code'] == 'SCOPE_VIOLATION'
    assert task_result['error']['details']['violations'] == ['algorithm/chat/prompts/rewrite.py']


def test_execute_simple_report_retries_until_validation_passes(
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
                'module': 'retriever',
                'goal': 'needs two rounds',
                'plan': ['append twice until validation passes'],
                'change_targets': [{'file': ALLOWED_FILE}],
                'validation': [f'test "$(grep -c updated {ALLOWED_FILE})" -eq 2'],
            }
        ],
    )

    outcome = execute_simple_report(
        payload,
        repo_path=str(temp_algorithm_repo),
        instruction='完成这个json内的任务',
        max_rounds=2,
        artifact_root=str(tmp_path / 'artifacts'),
    )

    assert outcome['status'] == 'SUCCEEDED'
    task_result = outcome['task_results'][0]
    assert task_result['status'] == 'SUCCEEDED'
    assert task_result['rounds'] == 2
    assert task_result['validation_result']['status'] == 'PASSED'


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
                        'module': 'retriever',
                        'goal': 'cli run',
                        'plan': ['run with cli'],
                        'change_targets': [{'file': ALLOWED_FILE}],
                        'validation': [f'grep -q updated {ALLOWED_FILE}'],
                    }
                ],
            ),
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f'{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else str(PROJECT_ROOT)

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
    assert rendered['task_results'][0]['result']['files_changed'] == [ALLOWED_FILE]
