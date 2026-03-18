import os
import sys
import urllib.request

import requests

ALGO_ID = 'algo1'


def _ensure_ok(url: str) -> None:
    with urllib.request.urlopen(url, timeout=3) as response:
        if not (200 <= response.status < 300):
            raise RuntimeError(f'unhealthy endpoint: {url} status={response.status}')


def main() -> int:
    algo_port = int(os.getenv('LAZYRAG_ALGO_SERVER_PORT', os.getenv('LAZYRAG_DOCUMENT_SERVER_PORT', '8000')))
    processor_url = os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000').rstrip('/')

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
