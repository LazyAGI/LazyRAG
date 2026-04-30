"""Dataset (knowledge base) commands: kb-create, kb-list, kb-delete."""

import argparse
import sys
from urllib.parse import quote, urlencode

from cli import context
from cli.client import auth_request, print_json
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset


def cmd_kb_create(args: argparse.Namespace) -> int:
    payload: dict = {
        'display_name': args.name,
        'desc': args.desc or '',
    }
    # Only send `algo` when the user explicitly chose an algo_id.  The
    # backend substitutes `__default__` when the field is absent, and that
    # is the right fallback — binding to the retrieve-side `algo_dataset`
    # default (`general_algo`) would regress deployments that only expose
    # the backend's own default.
    if args.algo_id:
        payload['algo'] = {'algo_id': args.algo_id}

    query = ''
    if args.dataset_id:
        query = f'?{urlencode({"dataset_id": args.dataset_id})}'

    data = auth_request(
        'POST',
        f'{CORE_API_PREFIX}/datasets{query}',
        server=args.server,
        payload=payload,
    )
    ds = data.get('data', data)
    dataset_id = ds.get('dataset_id', '')

    # Auto-set as active dataset
    if dataset_id:
        context.set_key('dataset', dataset_id)

    if getattr(args, 'as_json', False):
        print_json(ds)
    else:
        print(
            f'Created dataset:  '
            f'dataset_id={dataset_id}  '
            f'name={ds.get("display_name")}'
        )
        if dataset_id:
            print(f'Active dataset set to {dataset_id}')
    return 0


def cmd_kb_delete(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    if not args.yes:
        if not sys.stdin.isatty():
            print(
                'Error: use -y to confirm deletion in non-interactive mode',
                file=sys.stderr,
            )
            return 1
        answer = input(
            f'Delete dataset {dataset_id!r} and all its documents? [y/N] '
        )
        if answer.strip().lower() not in ('y', 'yes'):
            print('Aborted.', file=sys.stderr)
            return 1

    auth_request(
        'DELETE',
        f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}',
        server=args.server,
    )

    # Clear active dataset if it was the deleted one
    if context.get('dataset') == dataset_id:
        context.unset_key('dataset')

    if getattr(args, 'as_json', False):
        print_json({'deleted': dataset_id})
    else:
        print(f'Deleted dataset {dataset_id}')
    return 0


def cmd_kb_list(args: argparse.Namespace) -> int:
    query = {'page_size': str(args.page_size)}
    if args.page is not None:
        query['page'] = str(args.page)
    params = f'?{urlencode(query)}'
    data = auth_request(
        'GET',
        f'{CORE_API_PREFIX}/datasets{params}',
        server=args.server,
    )
    # core service may wrap in envelope or return directly
    body = data.get('data', data)
    datasets = body.get('datasets') or []
    total = body.get('total', len(datasets))

    if getattr(args, 'as_json', False):
        print_json(body)
        return 0
    if not datasets:
        print('No datasets found.')
        return 0
    print(f'Datasets (showing {len(datasets)} of {total}):')
    for ds in datasets:
        algo = ds.get('algo') or {}
        print(
            f'  {ds.get("dataset_id")}  '
            f'name={ds.get("display_name")!r}  '
            f'docs={ds.get("document_count", 0)}  '
            f'algo={algo.get("algo_id", "-")}'
        )
    return 0
