"""LazyRAG CLI entry point: argument parsing and command dispatch."""

import argparse
import sys
from typing import Optional, Sequence

from cli.client import ApiError, print_json
from cli.commands.auth import cmd_login, cmd_logout, cmd_register, cmd_whoami
from cli.commands.dataset import cmd_kb_create, cmd_kb_list
from cli.commands.upload import cmd_task_get, cmd_task_list, cmd_upload


def _add_server_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--server', metavar='URL',
        help='LazyRAG server URL (default: http://localhost:8000)',
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='lazyrag',
        description='LazyRAG CLI - manage knowledge bases and documents',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # ---- auth ----
    reg = sub.add_parser('register', help='Create a new user account')
    _add_server_arg(reg)
    reg.add_argument('--username', '-u')
    reg.add_argument('--password', '-p')
    reg.add_argument('--email')
    reg.add_argument(
        '--no-login', action='store_true',
        help='Do not auto-login after registration',
    )
    reg.set_defaults(func=cmd_register)

    login = sub.add_parser('login', help='Log in and store credentials')
    _add_server_arg(login)
    login.add_argument('--username', '-u')
    login.add_argument('--password', '-p')
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser('logout', help='Log out and clear credentials')
    _add_server_arg(logout)
    logout.set_defaults(func=cmd_logout)

    whoami = sub.add_parser('whoami', help='Show current user info')
    _add_server_arg(whoami)
    whoami.add_argument('--json', dest='as_json', action='store_true')
    whoami.set_defaults(func=cmd_whoami)

    # ---- dataset / kb ----
    kb_create = sub.add_parser(
        'kb-create', help='Create a knowledge base (dataset)',
    )
    _add_server_arg(kb_create)
    kb_create.add_argument('--name', required=True, help='Display name')
    kb_create.add_argument('--desc', help='Description')
    kb_create.add_argument('--algo-id', help='Algorithm ID')
    kb_create.add_argument(
        '--dataset-id', help='Custom dataset ID (auto-generated if omitted)',
    )
    kb_create.set_defaults(func=cmd_kb_create)

    kb_list = sub.add_parser('kb-list', help='List knowledge bases')
    _add_server_arg(kb_list)
    kb_list.add_argument('--page-size', type=int, default=100)
    kb_list.add_argument('--json', dest='as_json', action='store_true')
    kb_list.set_defaults(func=cmd_kb_list)

    # ---- upload ----
    upload = sub.add_parser(
        'upload', help='Upload a local directory into a dataset',
    )
    _add_server_arg(upload)
    upload.add_argument(
        '--dataset', required=True,
        help='Target dataset ID',
    )
    upload.add_argument(
        '--dir', '--directory', dest='directory', required=True,
        help='Local directory to upload',
    )
    upload.add_argument(
        '--extensions',
        help='Comma-separated file extensions to include (e.g. pdf,docx,txt)',
    )
    upload.add_argument('--limit', type=int, help='Max files to upload')
    upload.add_argument(
        '--recursive', dest='recursive',
        action='store_true', default=True,
    )
    upload.add_argument(
        '--no-recursive', dest='recursive', action='store_false',
    )
    upload.add_argument('--include-hidden', action='store_true')
    upload.add_argument(
        '--wait', action='store_true',
        help='Wait for parsing tasks to complete',
    )
    upload.add_argument('--wait-interval', type=float, default=3.0)
    upload.add_argument('--wait-timeout', type=float, default=0.0)
    upload.add_argument('--timeout', type=float, default=300.0)
    upload.set_defaults(func=cmd_upload)

    # ---- task ----
    task_list = sub.add_parser('task-list', help='List tasks in a dataset')
    _add_server_arg(task_list)
    task_list.add_argument('--dataset', required=True)
    task_list.add_argument('--page-size', type=int, default=100)
    task_list.add_argument('--json', dest='as_json', action='store_true')
    task_list.set_defaults(func=cmd_task_list)

    task_get = sub.add_parser('task-get', help='Get details of a single task')
    _add_server_arg(task_get)
    task_get.add_argument('--dataset', required=True)
    task_get.add_argument('task_id')
    task_get.set_defaults(func=cmd_task_get)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ApiError as exc:
        print(f'API error ({exc.status_code}): {exc}', file=sys.stderr)
        if exc.payload:
            print_json(exc.payload)
        return 1
    except KeyboardInterrupt:
        print('\nAborted.', file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f'Error: {exc}', file=sys.stderr)
        return 1
