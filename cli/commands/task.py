"""Task lifecycle commands: task-cancel, task-resume."""

import argparse
from urllib.parse import quote

from cli.client import auth_request, print_json
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset


def _call_task_action(
    dataset_id: str,
    task_id: str,
    action: str,
    server=None,
):
    """Post to /tasks/{task}:<action>.

    Both IDs are user-controlled (dataset via `lazyrag use` / --dataset,
    task via CLI argument), so they go through ``quote(..., safe='')``
    before interpolation to prevent path injection or accidental 404s on
    IDs containing ``/``, ``#``, or spaces.
    """
    path = (
        f'{CORE_API_PREFIX}/datasets/{quote(str(dataset_id), safe="")}'
        f'/tasks/{quote(str(task_id), safe="")}:{action}'
    )
    return auth_request('POST', path, server=server)


def cmd_task_cancel(args: argparse.Namespace) -> int:
    """Cancel a running task (backend endpoint :suspend → CANCELED)."""
    dataset_id = resolve_dataset(args.dataset)
    data = _call_task_action(
        dataset_id, args.task_id, 'suspend', server=args.server,
    )
    if args.as_json:
        print_json({'task_id': args.task_id, 'result': data})
    else:
        print(f'Cancelled task {args.task_id}')
    return 0


def cmd_task_resume(args: argparse.Namespace) -> int:
    """Resume a suspended task."""
    dataset_id = resolve_dataset(args.dataset)
    data = _call_task_action(
        dataset_id, args.task_id, 'resume', server=args.server,
    )
    if args.as_json:
        print_json({'task_id': args.task_id, 'result': data})
    else:
        print(f'Resumed task {args.task_id}')
    return 0
