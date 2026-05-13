from pathlib import Path

import pytest

from evo.log_collector import PytestResultChecker, check_pytest_log_passed, main


def test_check_pytest_log_passed_uses_last_non_empty_line():
    log = """
    FAILED tests/test_before.py::test_old - AssertionError

    ========== 3 passed in 0.12s ==========
    """

    assert check_pytest_log_passed(log) is True


def test_check_pytest_log_passed_detects_failure_on_last_non_empty_line():
    log = """
    ========== 4 passed in 0.15s ==========

    ========== 1 failed, 4 passed in 0.20s ==========
    """

    assert check_pytest_log_passed(log) is False


def test_check_pytest_log_passed_reads_from_path(tmp_path):
    log_path = tmp_path / 'pytest.log'
    log_path.write_text('setup output\n\n========== 2 passed in 0.08s ==========\n', encoding='utf-8')

    assert check_pytest_log_passed(log_path=log_path) is True
    assert check_pytest_log_passed(Path(log_path)) is True


def test_check_pytest_log_passed_requires_log_or_path():
    with pytest.raises(ValueError, match='Either log or log_path must be provided'):
        check_pytest_log_passed()


def test_pytest_result_checker_delegates_to_log_check():
    checker = PytestResultChecker()

    assert checker('========== 1 passed in 0.01s ==========') is True
    assert checker('========== 1 failed in 0.01s ==========') is False


def test_main_returns_zero_for_passing_log(tmp_path):
    log_path = tmp_path / 'pytest.log'
    log_path.write_text('========== 1 passed in 0.01s ==========\n', encoding='utf-8')

    assert main([str(log_path)]) == 0


def test_main_returns_one_for_failing_log(tmp_path):
    log_path = tmp_path / 'pytest.log'
    log_path.write_text('========== 1 failed in 0.01s ==========\n', encoding='utf-8')

    assert main([str(log_path)]) == 1
