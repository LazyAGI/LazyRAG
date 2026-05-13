import sys

import requests

from config import config as _cfg

ALGO_ID = 'general_algo'


def _ensure_ok(url: str) -> None:
    response = requests.get(url, timeout=3)
    response.raise_for_status()


def main() -> int:
    algo_port = _cfg['algo_server_port'] or _cfg['document_server_port']
    processor_url = _cfg['document_processor_url'].rstrip('/')

    _ensure_ok(f'http://127.0.0.1:{algo_port}/docs')
    response = requests.get(f'{processor_url}/algo/list', timeout=3)
    response.raise_for_status()
    items = response.json().get('data', [])
    if not any(item.get('algo_id') == ALGO_ID for item in items):
        raise RuntimeError(f'algo_id not registered yet: {ALGO_ID}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
