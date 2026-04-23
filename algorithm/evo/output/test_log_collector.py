"""Check pytest logs by looking at the last non-empty line."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    import lazyllm
    from lazyllm import ModuleBase
except Exception:  # pragma: no cover - LazyLLM is optional here.
    lazyllm = None
    ModuleBase = object


DEFAULT_LOG_PATH = Path(__file__).resolve().parent / 'output' / 'val' / 'test.log'


class PytestResultChecker(ModuleBase):
    """Module wrapper: return False if the log's last line contains failed."""

    def __init__(self, *, return_trace: bool = False) -> None:
        if lazyllm is not None:
            super().__init__(return_trace=return_trace)

    def __call__(self, log: str | Path | None = None, *, log_path: str | Path | None = None) -> bool:
        return self.forward(log=log, log_path=log_path)

    def forward(self, log: str | Path | None = None, *, log_path: str | Path | None = None, **_: Any) -> bool:
        return check_pytest_log_passed(log=log, log_path=log_path)


def check_pytest_log_passed(log: str | Path | None = None, *, log_path: str | Path | None = None) -> bool:
    """Return True unless the last non-empty line contains failed."""
    return 'failed' not in _last_line(_read_log(log=log, log_path=log_path)).lower()


def _read_log(log: str | Path | None = None, *, log_path: str | Path | None = None) -> str:
    if log_path is not None:
        return Path(log_path).read_text(encoding='utf-8')
    if isinstance(log, Path):
        return log.read_text(encoding='utf-8')
    if log is None:
        raise ValueError('Either log or log_path must be provided.')
    return str(log)


def _last_line(log_text: str) -> str:
    return next((line.strip() for line in reversed(log_text.splitlines()) if line.strip()), '')


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Check pytest log result from the last line.')
    parser.add_argument('log_path', nargs='?', default=str(DEFAULT_LOG_PATH), help='Pytest log path, or - for stdin.')
    args = parser.parse_args(argv)

    log_text = sys.stdin.read() if args.log_path == '-' else Path(args.log_path).read_text(encoding='utf-8')

    # Simulate the full pipeline: instantiate the module and call it with upstream log content.
    passed = PytestResultChecker()(log_text)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
