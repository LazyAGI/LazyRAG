"""Chunk command: list parsed segments (chunks) of a document."""

import argparse
from urllib.parse import urlencode
from typing import Any, Dict, List

from cli.client import auth_request, print_json
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset


def _truncate(text: str, width: int = 80) -> str:
    text = text.replace('\n', ' ').replace('\r', '')
    if len(text) <= width:
        return text
    return text[:width - 3] + '...'


def _print_table(segments: List[Dict[str, Any]]) -> None:
    if not segments:
        print('No segments found.')
        return

    header = f'{"#":<4} {"segment_id":<36} {"status":<10} {"words":<6} {"content"}'
    print(header)
    print('-' * min(len(header) + 40, 120))
    for i, seg in enumerate(segments, 1):
        sid = seg.get('segment_id', seg.get('id', ''))[:36]
        status = seg.get('status', '')
        word_count = seg.get('word_count', seg.get('tokens', ''))
        content = _truncate(seg.get('content', ''), 60)
        print(f'{i:<4} {sid:<36} {status:<10} {str(word_count):<6} {content}')


def cmd_chunk(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    document_id = args.document

    path = (
        f'{CORE_API_PREFIX}/datasets/{dataset_id}'
        f'/documents/{document_id}/segments'
    )
    params = {'page_size': str(args.page_size)}
    if args.page:
        params['page'] = str(args.page)
    path = f'{path}?{urlencode(params)}'

    data = auth_request('GET', path, server=args.server)

    if args.as_json:
        print_json(data)
        return 0

    segments = data.get('segments') or data.get('list', data.get('data', []))
    if isinstance(segments, dict):
        segments = segments.get('segments') or segments.get('list', [])

    total = data.get('total_size', data.get('total', len(segments)))
    print(f'Segments (showing {len(segments)} of {total}):')
    _print_table(segments)
    return 0
