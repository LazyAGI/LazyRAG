"""Chunk command: list parsed segments (chunks) of a document."""

import argparse
from urllib.parse import quote, urlencode
from typing import Any, Dict, List

from cli.client import auth_request, print_json
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset


def _truncate(text: str, width: int = 80) -> str:
    text = (text or '').replace('\n', ' ').replace('\r', '')
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
        sid = str(seg.get('segment_id') or seg.get('id') or '')[:36]
        status = str(seg.get('status') or '')
        word_count = seg.get('word_count') or seg.get('tokens') or ''
        content = _truncate(seg.get('content') or '', 60)
        print(f'{i:<4} {sid:<36} {status:<10} {str(word_count):<6} {content}')


def cmd_chunk(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    document_id = args.document

    path = (
        f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}'
        f'/documents/{quote(document_id, safe="")}/segments'
    )
    params = {'page_size': str(args.page_size)}
    if args.page is not None:
        params['page'] = str(args.page)
    path = f'{path}?{urlencode(params)}'

    data = auth_request('GET', path, server=args.server)

    if args.as_json:
        print_json(data)
        return 0

    segments = data.get('segments')
    if segments is None:
        segments = data.get('list')
    if segments is None:
        segments = data.get('data', [])
    if isinstance(segments, dict):
        inner = segments.get('segments')
        if inner is None:
            inner = segments.get('list', [])
        segments = inner

    total = data.get('total_size', data.get('total', len(segments)))
    print(f'Segments (showing {len(segments)} of {total}):')
    _print_table(segments)
    return 0
