"""Standalone DocServer launcher for LazyRAG.

This entrypoint runs LazyLLM's DocServer as an independent Python service and
connects it to a remote parsing/processor service.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[3]
ALGORITHM_ROOT = REPO_ROOT / 'algorithm'
LAZYLLM_ROOT = ALGORITHM_ROOT / 'lazyllm'

for path in (str(LAZYLLM_ROOT), str(ALGORITHM_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from common.db import require_shared_db_config  # noqa: E402
from lazyllm.tools.rag.doc_service import DocServer  # noqa: E402


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value and value.strip() else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value and value.strip() else default


def _default_storage_dir() -> str:
    return (
        os.getenv('LAZYRAG_DOCUMENT_SERVICE_STORAGE_DIR')
        or os.getenv('LAZYRAG_UPLOAD_DIR')
        or str(REPO_ROOT / '.lazyrag' / 'uploads')
    )


def build_doc_server(
    *,
    port: Optional[int] = None,
    parser_url: Optional[str] = None,
    callback_url: Optional[str] = None,
) -> DocServer:
    resolved_port = port or _env_int('LAZYRAG_DOCUMENT_SERVICE_PORT', 8000)
    resolved_parser_url = parser_url or os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000')
    resolved_callback_url = callback_url or os.getenv('LAZYRAG_DOCUMENT_SERVICE_CALLBACK_URL')
    db_config = require_shared_db_config('DocServer')

    return DocServer(
        port=resolved_port,
        parser_url=resolved_parser_url,
        db_config=db_config,
        parser_db_config=db_config,
        parser_poll_interval=_env_float('LAZYRAG_DOCUMENT_SERVICE_PARSER_POLL_INTERVAL', 0.05),
        storage_dir=_default_storage_dir(),
        callback_url=resolved_callback_url,
    )


def _resolve_runtime_callback_url(callback_url: Optional[str]) -> Optional[str]:
    return callback_url or os.getenv('LAZYRAG_DOCUMENT_SERVICE_CALLBACK_URL')


def main() -> None:
    parser = argparse.ArgumentParser(description='Run LazyRAG standalone DocServer.')
    parser.add_argument(
        '--port',
        type=int,
        default=_env_int('LAZYRAG_DOCUMENT_SERVICE_PORT', 8000),
        help='DocServer listen port.',
    )
    parser.add_argument(
        '--parser-url',
        type=str,
        default=os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000'),
        help='Remote DocumentProcessor base URL.',
    )
    parser.add_argument(
        '--callback-url',
        type=str,
        default=os.getenv('LAZYRAG_DOCUMENT_SERVICE_CALLBACK_URL'),
        help='Optional callback URL override.',
    )
    parser.add_argument(
        '--export-openapi',
        type=str,
        default=None,
        help='Export DocServer OpenAPI JSON and exit.',
    )
    args = parser.parse_args()

    if args.export_openapi:
        output_path = DocServer.export_openapi(args.export_openapi)
        print(f'OpenAPI exported: {output_path}', flush=True)
        return

    stop_event = threading.Event()
    doc_server = build_doc_server(
        port=args.port,
        parser_url=args.parser_url,
        callback_url=args.callback_url,
    )

    def _handle_signal(signum, frame):
        stop_event.set()
        try:
            doc_server.stop()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    doc_server.start()
    runtime_callback_url = _resolve_runtime_callback_url(args.callback_url)
    if runtime_callback_url:
        try:
            doc_server._dispatch('set_runtime_callback_url', runtime_callback_url)
        except Exception as exc:
            print(f'Failed to set runtime callback url: {exc}', flush=True)
    base_url = doc_server.url.rsplit('/', 1)[0]

    print(f'DocServer URL: {base_url}', flush=True)
    print(f'DocServer Docs: {base_url}/docs', flush=True)
    print(f'Processor URL: {args.parser_url}', flush=True)
    print(f'Callback URL: {runtime_callback_url or "(auto)"}', flush=True)
    print(f'Storage Dir: {_default_storage_dir()}', flush=True)
    print('DocServer is running. Press Ctrl+C to stop...', flush=True)

    stop_event.wait()


if __name__ == '__main__':
    main()
