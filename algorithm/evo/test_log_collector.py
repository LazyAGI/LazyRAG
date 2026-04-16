"""Convert pytest logs into compact pass/fail JSON summaries."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
try:
    import lazyllm
    from lazyllm import ModuleBase
except Exception:  # pragma: no cover - LazyLLM is optional for log parsing.
    lazyllm = None
    ModuleBase = object


_DEFAULT_CODE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = _DEFAULT_CODE_ROOT / 'algorithm' / 'evo' / 'output' / 'test'
_NODEID_RE = re.compile(
    r'(?P<nodeid>(?:[\w./\\-]+\.py)::[^\s:]+)(?:\s+-\s+|\s+(?P<word>FAILED|ERROR)\b)',
    flags=re.MULTILINE,
)
_SUMMARY_RE = re.compile(
    r'^(?P<outcome>FAILED|ERROR)\s+(?P<nodeid>(?:[\w./\\-]+\.py)::[^\s]+)'
    r'(?:\s+-\s+(?P<message>.*))?$',
    flags=re.MULTILINE,
)
_PROGRESS_RE = re.compile(
    r'^(?P<nodeid>(?:[\w./\\-]+\.py)::[^\s]+)\s+(?P<outcome>FAILED|ERROR)\b',
    flags=re.MULTILINE,
)
_SECTION_RE = re.compile(
    r'^_{2,}\s+(?P<name>test[^\s\[]*(?:\[[^\]]+\])?)\s+_{2,}$',
    flags=re.MULTILINE,
)
_PASS_SUMMARY_RE = re.compile(
    r'=+\s+(?:(?:\d+\s+\w+,\s+)*\d+\s+passed|no tests ran)\b[^=]*=+',
    flags=re.IGNORECASE,
)
_FAIL_SUMMARY_RE = re.compile(
    r'\b(?:failed|error|errors|interrupted)\b',
    flags=re.IGNORECASE,
)
DEFAULT_PASS_IDENTIFIER = 'PYTEST_ALL_PASSED'


class PytestLogCollector(ModuleBase):
    """Module wrapper that returns a pass identifier or the complete pytest log."""

    def __init__(
        self,
        output: str | Path | None = None,
        *,
        pass_identifier: str = DEFAULT_PASS_IDENTIFIER,
        return_trace: bool = False,
    ) -> None:
        if lazyllm is not None:
            super().__init__(return_trace=return_trace)
        self.output = output
        self.pass_identifier = pass_identifier

    def forward(
        self,
        log: str | Path | None = None,
        *,
        log_path: str | Path | None = None,
        output: str | Path | None = None,
        output_path: str | Path | None = None,
        command: Optional[Sequence[str] | str] = None,
        return_code: Optional[int] = None,
        target: str = '',
        pass_identifier: str | None = None,
    ) -> Dict[str, Any]:
        """Convert a pytest log path or raw pytest log text into JSON data."""
        result = collect_pytest_log(
            log=log,
            log_path=log_path,
            command=command,
            return_code=return_code,
            target=target,
            pass_identifier=pass_identifier or self.pass_identifier,
        )
        resolved_output = output_path or output or self.output
        if resolved_output:
            write_json(result, resolved_output)
        return result


def collect_pytest_log(
    log: str | Path | None = None,
    *,
    log_path: str | Path | None = None,
    command: Optional[Sequence[str] | str] = None,
    return_code: Optional[int] = None,
    target: str = '',
    pass_identifier: str = DEFAULT_PASS_IDENTIFIER,
) -> Dict[str, Any]:
    """Convert either raw pytest log text or a pytest log path into JSON data."""
    if log_path is not None:
        path = Path(log_path)
        return summarize_pytest_log(
            path.read_text(encoding='utf-8'),
            command=_normalize_command(command),
            target=target,
            return_code=return_code,
            log_path=path,
            pass_identifier=pass_identifier,
        )
    if log is None:
        raise ValueError('Either `log` or `log_path` must be provided.')
    if isinstance(log, Path):
        return collect_pytest_log(
            log_path=log,
            command=command,
            return_code=return_code,
            target=target,
            pass_identifier=pass_identifier,
        )
    return summarize_pytest_log(
        str(log),
        command=_normalize_command(command),
        target=target,
        return_code=return_code,
        pass_identifier=pass_identifier,
    )


def convert_pytest_log(
    log_path: str | Path,
    *,
    output: str | Path | None = None,
    command: Optional[Sequence[str] | str] = None,
    return_code: Optional[int] = None,
    pass_identifier: str = DEFAULT_PASS_IDENTIFIER,
) -> Dict[str, Any]:
    """Read an existing pytest log file and write a JSON-compatible summary."""
    result = collect_pytest_log(
        log_path=log_path,
        command=command,
        return_code=return_code,
        pass_identifier=pass_identifier,
    )
    if output:
        write_json(result, output)
    return result


def summarize_pytest_log(
    log_text: str,
    *,
    command: Optional[Sequence[str]] = None,
    target: str = '',
    return_code: Optional[int] = None,
    log_path: str | Path | None = None,
    pass_identifier: str = DEFAULT_PASS_IDENTIFIER,
) -> Dict[str, Any]:
    """Return a pass identifier for passing pytest logs, otherwise full log."""
    passed = _pytest_log_passed(log_text, return_code=return_code)
    result: Dict[str, Any] = {
        'status': 'passed' if passed else 'failed',
        'result': pass_identifier if passed else log_text,
        'target': target,
        'command': list(command or []),
        'return_code': return_code,
        'passed': passed,
    }
    if log_path:
        result['log_path'] = str(Path(log_path))
    return result


def parse_failed_tests(log_text: str) -> List[Dict[str, str]]:
    """Extract failed/error pytest node ids from a captured log."""
    failures: Dict[str, Dict[str, str]] = {}
    section_names = {match.group('name') for match in _SECTION_RE.finditer(log_text)}

    for match in _SUMMARY_RE.finditer(log_text):
        _add_failure(
            failures,
            match.group('nodeid'),
            match.group('outcome'),
            match.group('message') or '',
        )

    for match in _PROGRESS_RE.finditer(log_text):
        _add_failure(failures, match.group('nodeid'), match.group('outcome'), '')

    for match in _NODEID_RE.finditer(log_text):
        outcome = match.group('word') or _infer_outcome_from_context(log_text, match.start())
        _add_failure(failures, match.group('nodeid'), outcome, '')

    if not failures and section_names:
        for name in sorted(section_names):
            _add_failure(failures, name, 'FAILED', '')

    return sorted(failures.values(), key=lambda item: item['nodeid'])


def write_json(value: Mapping[str, Any], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def _add_failure(
    failures: Dict[str, Dict[str, str]],
    nodeid: str,
    outcome: str,
    message: str,
) -> None:
    clean_nodeid = nodeid.strip()
    if not clean_nodeid:
        return
    file_path, test_function = _split_nodeid(clean_nodeid)
    current = failures.get(clean_nodeid)
    payload = {
        'nodeid': clean_nodeid,
        'file': file_path,
        'test_function': test_function,
        'outcome': outcome.upper(),
        'message': message.strip(),
    }
    if current and current.get('message'):
        payload['message'] = current['message']
    failures[clean_nodeid] = payload


def _split_nodeid(nodeid: str) -> tuple[str, str]:
    if '::' not in nodeid:
        return '', nodeid
    file_path, rest = nodeid.split('::', 1)
    return file_path, rest.split('::')[-1]


def _infer_outcome_from_context(log_text: str, start: int) -> str:
    line_start = log_text.rfind('\n', 0, start) + 1
    line_end = log_text.find('\n', start)
    if line_end < 0:
        line_end = len(log_text)
    line = log_text[line_start:line_end]
    return 'ERROR' if 'ERROR' in line else 'FAILED'


def _first_error_line(log_text: str) -> str:
    for line in log_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(('ERROR', 'INTERNALERROR', 'E   ', 'ImportError', 'ModuleNotFoundError')):
            return stripped
    return ''


def _pytest_log_passed(log_text: str, *, return_code: Optional[int] = None) -> bool:
    if return_code is not None:
        return return_code == 0 and not _first_error_line(log_text)
    if _first_error_line(log_text):
        return False
    if parse_failed_tests(log_text):
        return False
    summary_tail = _pytest_summary_tail(log_text)
    return bool(_PASS_SUMMARY_RE.search(log_text)) and not _FAIL_SUMMARY_RE.search(summary_tail)


def _pytest_summary_tail(log_text: str) -> str:
    lines = log_text.strip().splitlines()
    return '\n'.join(lines[-20:])


def _normalize_command(command: Optional[Sequence[str] | str]) -> List[str]:
    if command is None:
        return []
    if isinstance(command, str):
        return [command]
    return [str(item) for item in command]


def _default_output_path(log_path: str | Path) -> Path:
    path = Path(log_path)
    stem = 'stdin' if str(log_path) == '-' else path.stem
    return _DEFAULT_OUTPUT_DIR / f'{stem}_summary.json'


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description='Convert an existing pytest log into a pass/fail JSON summary.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('log_path', help='Existing pytest log path, or - for stdin.')
    parser.add_argument('--output', help='JSON output path.')
    parser.add_argument('--command', action='append', default=[],
                        help='Optional original pytest command to store in JSON.')
    parser.add_argument('--return-code', type=int,
                        help='Optional pytest process return code if known.')
    parser.add_argument('--pass-identifier', default=DEFAULT_PASS_IDENTIFIER,
                        help='Identifier returned when the pytest log passed.')
    args = parser.parse_args(argv)

    if args.log_path == '-':
        log_text = sys.stdin.read()
        result = summarize_pytest_log(
            log_text,
            command=args.command,
            return_code=args.return_code,
            log_path=None,
            pass_identifier=args.pass_identifier,
        )
    else:
        result = convert_pytest_log(
            args.log_path,
            output=None,
            command=args.command,
            return_code=args.return_code,
            pass_identifier=args.pass_identifier,
        )
    output = args.output or _default_output_path(args.log_path)
    write_json(result, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
