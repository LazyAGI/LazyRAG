"""Dataset (knowledge base) commands: kb-create, kb-list."""

import argparse

from cli.client import auth_request, print_json
from cli.config import CORE_API_PREFIX


def cmd_kb_create(args: argparse.Namespace) -> int:
    payload = {
        'display_name': args.name,
        'desc': args.desc or '',
    }
    if args.algo_id:
        payload['algo'] = {'algo_id': args.algo_id}

    query = ''
    if args.dataset_id:
        query = f'?dataset_id={args.dataset_id}'

    data = auth_request(
        'POST',
        f'{CORE_API_PREFIX}/datasets{query}',
        server=args.server,
        payload=payload,
    )
    ds = data.get('data', data)
    print(
        f'Created dataset:  '
        f'dataset_id={ds.get("dataset_id")}  '
        f'name={ds.get("display_name")}'
    )
    return 0


def cmd_kb_list(args: argparse.Namespace) -> int:
    params = f'?page_size={args.page_size}'
    data = auth_request(
        'GET',
        f'{CORE_API_PREFIX}/datasets{params}',
        server=args.server,
    )
    # core service may wrap in envelope or return directly
    body = data.get('data', data)
    datasets = body.get('datasets') or []

    if args.as_json:
        print_json(datasets)
        return 0
    if not datasets:
        print('No datasets found.')
        return 0
    for ds in datasets:
        algo = ds.get('algo') or {}
        print(
            f'{ds.get("dataset_id")}  '
            f'name={ds.get("display_name")!r}  '
            f'docs={ds.get("document_count", 0)}  '
            f'algo={algo.get("algo_id", "-")}'
        )
    return 0
