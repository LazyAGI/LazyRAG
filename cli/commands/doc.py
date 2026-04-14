"""Document commands: doc-list, doc-delete, doc-update."""

import argparse
import json
import sys
from typing import Any, Dict, List

from cli.client import auth_request, print_json
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, width: int = 40) -> str:
    text = (text or '').replace('\n', ' ').replace('\r', '')
    if len(text) <= width:
        return text
    return text[:width - 3] + '...'


def _print_docs(docs: List[Dict[str, Any]]) -> None:
    if not docs:
        print('No documents found.')
        return

    header = (
        f'{"#":<4} {"document_id":<36} {"status":<12} '
        f'{"segments":<9} {"name"}'
    )
    print(header)
    print('-' * min(len(header) + 20, 120))
    for i, doc in enumerate(docs, 1):
        did = str(doc.get('document_id', doc.get('id', '')))[:36]
        status = doc.get('status', '')
        seg_count = doc.get('segment_count', doc.get('completed_segments', ''))
        name = _truncate(doc.get('display_name', doc.get('name', '')), 50)
        print(f'{i:<4} {did:<36} {status:<12} {str(seg_count):<9} {name}')


# ---------------------------------------------------------------------------
# doc-list
# ---------------------------------------------------------------------------

def cmd_doc_list(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    params = f'?page_size={args.page_size}'
    if args.page:
        params += f'&page={args.page}'

    data = auth_request(
        'GET',
        f'{CORE_API_PREFIX}/datasets/{dataset_id}/documents{params}',
        server=args.server,
    )
    body = data.get('data', data)
    docs = body.get('documents', body.get('list', []))
    total = body.get('total', len(docs))

    if args.as_json:
        print_json(body)
        return 0

    print(f'Documents (showing {len(docs)} of {total}):')
    _print_docs(docs)
    return 0


# ---------------------------------------------------------------------------
# doc-delete
# ---------------------------------------------------------------------------

def cmd_doc_delete(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    document_id = args.document
    if not args.yes:
        if not sys.stdin.isatty():
            print(
                'Error: use -y to confirm deletion in non-interactive mode',
                file=sys.stderr,
            )
            return 1
        answer = input(
            f'Delete document {document_id!r} '
            f'from dataset {dataset_id!r}? [y/N] '
        )
        if answer.strip().lower() not in ('y', 'yes'):
            print('Aborted.', file=sys.stderr)
            return 1

    auth_request(
        'DELETE',
        f'{CORE_API_PREFIX}/datasets/{dataset_id}'
        f'/documents/{document_id}',
        server=args.server,
    )

    if getattr(args, 'as_json', False):
        print_json({'deleted': document_id, 'dataset': dataset_id})
    else:
        print(f'Deleted document {document_id}')
    return 0


# ---------------------------------------------------------------------------
# doc-update
# ---------------------------------------------------------------------------

def cmd_doc_update(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    document_id = args.document
    payload: Dict[str, Any] = {}
    if args.name is not None:
        payload['display_name'] = args.name
    if args.meta is not None:
        try:
            meta = json.loads(args.meta)
        except json.JSONDecodeError as exc:
            print(f'Invalid JSON for --meta: {exc}', file=sys.stderr)
            return 1
        payload['meta'] = meta

    if not payload:
        print('Nothing to update. Use --name or --meta.', file=sys.stderr)
        return 1

    data = auth_request(
        'PATCH',
        f'{CORE_API_PREFIX}/datasets/{dataset_id}'
        f'/documents/{document_id}',
        server=args.server,
        payload=payload,
    )
    doc = data.get('data', data)

    if getattr(args, 'as_json', False):
        print_json(doc)
    else:
        print(
            f'Updated document {document_id}  '
            f'name={doc.get("display_name", "")!r}'
        )
    return 0
