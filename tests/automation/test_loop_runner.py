from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from automation.opencode_adapter.loop_runner import run_report_fix_loop


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

    report_path = tmp_path / 'report.json'
    report_path.write_text(
        json.dumps(_report_payload(fake_opencode), ensure_ascii=False),
        encoding='utf-8',
    )

    check_script = tmp_path / 'check_repo.py'
    check_script.write_text(
        '\n'.join(
            [
                'from pathlib import Path',
                f'path = Path.cwd() / {ALLOWED_FILE!r}',
                "content = path.read_text(encoding='utf-8')",
                "if 'updated' in content:",
                "    print('=== 1 passed in 0.01s ===')",
                '    raise SystemExit(0)',
                "print('AssertionError: missing updated marker in retriever file')",
                "print('=== 1 failed in 0.01s ===')",
                'raise SystemExit(1)',
            ]
        ),
        encoding='utf-8',
    )

    outcome = run_report_fix_loop(
        str(report_path),
        str(temp_algorithm_repo),
        max_rounds=2,
        test_command=[sys.executable, str(check_script)],
        artifact_root=str(tmp_path / 'loop_artifacts'),
    )

    assert outcome['status'] == 'SUCCEEDED'
    assert outcome['round_count'] == 2
    assert outcome['last_result'] == {
        'files_changed': [ALLOWED_FILE],
        'change_summary': 'Fixed the failing test based on the full log.',
    }

    bundle_dir = Path(outcome['bundle_dir'])
    assert bundle_dir.exists()
    round_1_test_log = Path(outcome['rounds'][0]['test_log_path'])
    assert 'missing updated marker' in round_1_test_log.read_text(
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
