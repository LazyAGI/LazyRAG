from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


_TRACEBACK_HEAD = re.compile(r'^Traceback \(most recent call last\):', re.MULTILINE)
_PYTEST_FAILED = re.compile(r'^FAILED\s+(\S+)', re.MULTILINE)
_GO_FAILED = re.compile(r'^---\s+FAIL:\s+(\S+)', re.MULTILINE)

log = logging.getLogger('evo.apply.tests')


@dataclass
class TestOutcome:
    passed: bool
    returncode: int
    log_path: Path
    traceback_md_path: Path | None
    failed_tests: list[str] = field(default_factory=list)


def run_tests(repo_root: Path, artifact_dir: Path,
              command: Sequence[str] = ('bash', 'tests/run-all.sh'),
              *,
              on_proc: Callable[[subprocess.Popen], None] | None = None) -> TestOutcome:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log.info('running tests: cmd=%s cwd=%s', list(command), repo_root)
    proc = subprocess.Popen(
        list(command), cwd=str(repo_root),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    if on_proc:
        on_proc(proc)
    stdout, stderr = proc.communicate()
    log_text = '\n'.join(p for p in (stdout, stderr) if p)
    log_path = artifact_dir / 'test.log'
    log_path.write_text(log_text, encoding='utf-8')

    passed = proc.returncode == 0
    failed_tests = _extract_failed_tests(log_text) if not passed else []
    log.info('tests done: passed=%s returncode=%d failed_count=%d',
             passed, proc.returncode, len(failed_tests))

    traceback_md_path: Path | None = None
    if not passed:
        traceback_md_path = artifact_dir / 'traceback.md'
        traceback_md_path.write_text(
            _format_failure_report(log_text, failed_tests, max_lines=200),
            encoding='utf-8',
        )

    return TestOutcome(
        passed=passed,
        returncode=proc.returncode,
        log_path=log_path,
        traceback_md_path=traceback_md_path,
        failed_tests=failed_tests,
    )


def _extract_failed_tests(log_text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _PYTEST_FAILED.finditer(log_text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    for m in _GO_FAILED.finditer(log_text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _format_failure_report(log_text: str, failed_tests: list[str], *,
                           max_lines: int) -> str:
    sections: list[str] = []
    if failed_tests:
        sections.append('## 失败测试用例')
        sections.extend(f'- {n}' for n in failed_tests)
        sections.append('')

    sections.append('## Traceback')
    sections.append(_extract_traceback(log_text, max_lines=max_lines))
    return '\n'.join(sections).rstrip() + '\n'


def _extract_traceback(log_text: str, *, max_lines: int) -> str:
    matches = list(_TRACEBACK_HEAD.finditer(log_text))
    if not matches:
        tail = log_text.splitlines()[-max_lines:]
        return '\n'.join(tail).strip()

    chunks: list[str] = []
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(log_text)
        chunks.append(log_text[start:end].rstrip())

    joined = '\n\n'.join(chunks)
    lines = joined.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return '\n'.join(lines).strip()
