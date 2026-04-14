from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from automation.opencode_adapter import execute


def _load_payload(input_file: str | None) -> Dict[str, Any]:
    if input_file:
        return json.loads(Path(input_file).read_text(encoding='utf-8'))
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError('stdin is empty; provide JSON input via stdin or --input-file')
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the OpenCode adapter with JSON stdin/stdout.')
    parser.add_argument('--input-file', help='Read JSON payload from a file instead of stdin.')
    parser.add_argument('--output-file', help='Write JSON result to a file in addition to stdout.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print the JSON result.')
    args = parser.parse_args()

    try:
        payload = _load_payload(args.input_file)
    except Exception as exc:
        error = {
            'status': 'FAILED',
            'result': None,
            'error': {'code': 'OPENCODE_EXEC_FAILED', 'message': str(exc), 'details': {}},
            'artifacts_dir': '',
        }
        rendered = json.dumps(error, ensure_ascii=False, indent=2 if args.pretty else None)
        print(rendered)
        return 1

    outcome = execute(payload)
    rendered = json.dumps(outcome, ensure_ascii=False, indent=2 if args.pretty else None)
    print(rendered)
    if args.output_file:
        Path(args.output_file).write_text(rendered + '\n', encoding='utf-8')
    return 0 if outcome['status'] in {'SUCCEEDED', 'NO_CHANGE'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
