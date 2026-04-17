from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from automation.opencode_adapter.loop_runner import (
    DEFAULT_MAX_ROUNDS,
    run_report_fix_loop,
)
from automation.opencode_adapter.simple_runner import main as run_simple_cli


def _render_loop_outcome(outcome: dict, *, pretty: bool) -> int:
    print(json.dumps(outcome, ensure_ascii=False, indent=2 if pretty else None))
    return 0 if outcome.get('status') == 'SUCCEEDED' else 1


def _loop_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description='Run the iterative OpenCode fix loop.')
    parser.add_argument('report_json', help='Path to the upstream report JSON file.')
    parser.add_argument('--repo', help='Path to the repository to edit. Defaults to the current working directory.')
    parser.add_argument('--max-rounds', type=int, default=DEFAULT_MAX_ROUNDS, help='Maximum number of fix rounds.')
    parser.add_argument(
        '--tests-path',
        help='Optional pytest path override. When omitted, the loop runs "bash tests/run-all.sh".',
    )
    parser.add_argument(
        '--test-command',
        help='Optional shell-style command string used for each round, for example: "bash tests/run-all.sh".',
    )
    parser.add_argument('--artifact-root', help='Optional directory for loop artifacts.')
    parser.add_argument('--python-executable', help='Optional Python executable used for nested commands.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print the JSON output.')
    args = parser.parse_args(list(argv))

    repo_path = str(Path(args.repo).expanduser().resolve()) if args.repo else str(Path.cwd().resolve())
    test_command = shlex.split(args.test_command) if args.test_command else None
    outcome = run_report_fix_loop(
        report_json_path=args.report_json,
        repo_path=repo_path,
        max_rounds=args.max_rounds,
        tests_path=args.tests_path,
        test_command=test_command,
        artifact_root=args.artifact_root,
        python_executable=args.python_executable,
    )
    return _render_loop_outcome(outcome, pretty=args.pretty)


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if '--loop' in argv_list:
        argv_list.remove('--loop')
        return _loop_main(argv_list)
    return run_simple_cli(argv_list)


if __name__ == '__main__':
    raise SystemExit(main())
