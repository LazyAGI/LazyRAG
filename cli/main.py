"""LazyRAG CLI entry point: argument parsing and command dispatch."""

import argparse
import sys
from typing import Optional, Sequence

from cli.client import ApiError
from cli.commands.auth import cmd_login, cmd_logout, cmd_register, cmd_whoami
from cli.commands.chunk import cmd_chunk
from cli.commands.context import cmd_config, cmd_status, cmd_use
from cli.commands.dataset import cmd_kb_create, cmd_kb_delete, cmd_kb_list
from cli.commands.doc import cmd_doc_delete, cmd_doc_list, cmd_doc_update
from cli.commands.retrieve import cmd_retrieve
from cli.commands.run import cmd_run_list, cmd_run_undo
from cli.commands.task import cmd_task_cancel, cmd_task_resume
from cli.commands.upload import cmd_task_get, cmd_task_list, cmd_upload


def _add_server_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--server', metavar='URL',
        help='LazyRAG server URL (default: from login)',
    )


def _add_dataset_arg(parser: argparse.ArgumentParser,
                     help_text: str = 'Dataset ID (default: from `lazyrag use`)') -> None:
    parser.add_argument('--dataset', default=None, help=help_text)


def _add_json_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--json', dest='as_json', action='store_true',
        help='Output as JSON (for scripting/agents)',
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='lazyrag',
        description='LazyRAG CLI - manage knowledge bases and documents',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # ---- context ----
    use = sub.add_parser('use', help='Set the active dataset')
    use.add_argument('dataset_id', help='Dataset ID to use as default')
    use.set_defaults(func=cmd_use)

    status = sub.add_parser('status', help='Show current CLI context')
    _add_json_arg(status)
    status.set_defaults(func=cmd_status)

    config = sub.add_parser('config', help='Manage CLI config')
    config_sub = config.add_subparsers(dest='config_action', required=True)

    config_list = config_sub.add_parser('list', help='Show all config values')
    _add_json_arg(config_list)
    config_list.set_defaults(func=cmd_config)

    config_get = config_sub.add_parser('get', help='Get a config value')
    config_get.add_argument('key')
    config_get.set_defaults(func=cmd_config)

    config_set = config_sub.add_parser('set', help='Set a config value')
    config_set.add_argument('key')
    config_set.add_argument('value')
    config_set.set_defaults(func=cmd_config)

    config_unset = config_sub.add_parser('unset', help='Remove a config value')
    config_unset.add_argument('key')
    config_unset.set_defaults(func=cmd_config)

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
    _add_json_arg(reg)
    reg.set_defaults(func=cmd_register)

    login = sub.add_parser('login', help='Log in and store credentials')
    _add_server_arg(login)
    login.add_argument('--username', '-u')
    login.add_argument('--password', '-p')
    _add_json_arg(login)
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser('logout', help='Log out and clear credentials')
    _add_server_arg(logout)
    logout.set_defaults(func=cmd_logout)

    whoami = sub.add_parser('whoami', help='Show current user info')
    _add_server_arg(whoami)
    _add_json_arg(whoami)
    whoami.set_defaults(func=cmd_whoami)

    # ---- dataset / kb ----
    kb_create = sub.add_parser(
        'kb-create', help='Create a knowledge base (auto-sets as active)',
    )
    _add_server_arg(kb_create)
    kb_create.add_argument('--name', required=True, help='Display name')
    kb_create.add_argument('--desc', help='Description')
    kb_create.add_argument(
        '--algo-id',
        help='Algorithm ID (defaults to algo_dataset config/env, usually general_algo)',
    )
    kb_create.add_argument(
        '--dataset-id', help='Custom dataset ID (auto-generated if omitted)',
    )
    _add_json_arg(kb_create)
    kb_create.set_defaults(func=cmd_kb_create)

    kb_list = sub.add_parser('kb-list', help='List knowledge bases')
    _add_server_arg(kb_list)
    kb_list.add_argument('--page-size', type=int, default=20)
    kb_list.add_argument('--page', type=int, default=None)
    _add_json_arg(kb_list)
    kb_list.set_defaults(func=cmd_kb_list)

    kb_delete = sub.add_parser(
        'kb-delete', help='Delete a knowledge base and all its documents',
    )
    _add_server_arg(kb_delete)
    _add_dataset_arg(kb_delete)
    kb_delete.add_argument(
        '-y', '--yes', action='store_true',
        help='Skip confirmation prompt',
    )
    _add_json_arg(kb_delete)
    kb_delete.set_defaults(func=cmd_kb_delete)

    # ---- document ----
    doc_list = sub.add_parser(
        'doc-list', help='List documents in a dataset',
    )
    _add_server_arg(doc_list)
    _add_dataset_arg(doc_list)
    doc_list.add_argument('--page-size', type=int, default=20)
    doc_list.add_argument('--page', type=int, default=None)
    _add_json_arg(doc_list)
    doc_list.set_defaults(func=cmd_doc_list)

    doc_delete = sub.add_parser(
        'doc-delete', help='Delete a document from a dataset',
    )
    _add_server_arg(doc_delete)
    _add_dataset_arg(doc_delete)
    doc_delete.add_argument('document', help='Document ID')
    doc_delete.add_argument(
        '-y', '--yes', action='store_true',
        help='Skip confirmation prompt',
    )
    _add_json_arg(doc_delete)
    doc_delete.set_defaults(func=cmd_doc_delete)

    doc_update = sub.add_parser(
        'doc-update', help='Update document metadata',
    )
    _add_server_arg(doc_update)
    _add_dataset_arg(doc_update)
    doc_update.add_argument('document', help='Document ID')
    doc_update.add_argument('--name', help='New display name')
    doc_update.add_argument(
        '--meta', help='Metadata as JSON string (e.g. \'{"key":"val"}\')',
    )
    _add_json_arg(doc_update)
    doc_update.set_defaults(func=cmd_doc_update)

    # ---- upload ----
    upload = sub.add_parser(
        'upload',
        help='Upload a local directory (stateful: resumable, dedup-aware)',
    )
    _add_server_arg(upload)
    _add_dataset_arg(upload, help_text='Target dataset ID')
    # Mode selection (mutually exclusive, enforced in cmd_upload)
    upload.add_argument(
        '--dir', '--directory', dest='directory', default=None,
        help='Local directory to upload',
    )
    upload.add_argument(
        '--resume', metavar='RUN_ID_OR_PATH', default=None,
        help='Resume an interrupted run (run_id or manifest path)',
    )
    upload.add_argument(
        '--retry-failed', dest='retry_failed', action='store_true',
        help='Re-upload only failed items from the latest run',
    )
    # Directory-scan options
    upload.add_argument(
        '--extensions',
        help='Comma-separated file extensions (e.g. pdf,docx,txt)',
    )
    upload.add_argument('--limit', type=int, help='Max files to upload')
    upload.add_argument(
        '--recursive', dest='recursive',
        action='store_true', default=True,
        help='Recurse into subdirectories (default)',
    )
    upload.add_argument(
        '--no-recursive', dest='recursive', action='store_false',
        help='Do not recurse into subdirectories',
    )
    upload.add_argument('--include-hidden', action='store_true')
    # Dedup options. Identical (existing) files are always skipped.
    upload.add_argument(
        '--replace-changed', dest='replace_changed', action='store_true',
        help='For changed files, delete remote version first and re-upload',
    )
    # Wait / polling options
    upload.add_argument(
        '--wait', action='store_true',
        help='Wait for parsing tasks to complete',
    )
    upload.add_argument(
        '--wait-interval', type=float, default=3.0,
        help='Polling interval in seconds while --wait (default: 3)',
    )
    upload.add_argument(
        '--wait-timeout', type=float, default=0.0,
        help='Max seconds to wait with --wait; 0 = no limit (default: 0)',
    )
    upload.add_argument(
        '--timeout', type=float, default=300.0,
        help='Per-file upload timeout in seconds (default: 300)',
    )
    # Output
    upload.add_argument(
        '--report-json', metavar='PATH', default=None,
        help='Write machine-readable report to this file',
    )
    _add_json_arg(upload)
    upload.set_defaults(func=cmd_upload)

    # ---- task ----
    task_list = sub.add_parser('task-list', help='List tasks in a dataset')
    _add_server_arg(task_list)
    _add_dataset_arg(task_list)
    task_list.add_argument('--page-size', type=int, default=20)
    _add_json_arg(task_list)
    task_list.set_defaults(func=cmd_task_list)

    task_get = sub.add_parser('task-get', help='Get details of a single task')
    _add_server_arg(task_get)
    _add_dataset_arg(task_get)
    task_get.add_argument('task_id')
    task_get.set_defaults(func=cmd_task_get)

    task_cancel = sub.add_parser('task-cancel', help='Cancel a running task')
    _add_server_arg(task_cancel)
    _add_dataset_arg(task_cancel)
    task_cancel.add_argument('task_id')
    _add_json_arg(task_cancel)
    task_cancel.set_defaults(func=cmd_task_cancel)

    task_resume = sub.add_parser('task-resume', help='Resume a suspended task')
    _add_server_arg(task_resume)
    _add_dataset_arg(task_resume)
    task_resume.add_argument('task_id')
    _add_json_arg(task_resume)
    task_resume.set_defaults(func=cmd_task_resume)

    # ---- run ----
    run_list = sub.add_parser(
        'run-list', help='List local upload runs',
    )
    _add_dataset_arg(run_list)
    run_list.add_argument(
        '--all', dest='all_datasets', action='store_true',
        help='List runs across all datasets',
    )
    _add_json_arg(run_list)
    run_list.set_defaults(func=cmd_run_list)

    run_undo = sub.add_parser(
        'run-undo', help='Delete all documents created by a run',
    )
    _add_server_arg(run_undo)
    run_undo.add_argument('run_id', help='Run ID or manifest path')
    run_undo.add_argument(
        '-y', '--yes', action='store_true',
        help='Skip confirmation prompt',
    )
    _add_json_arg(run_undo)
    run_undo.set_defaults(func=cmd_run_undo)

    # ---- chunk ----
    chunk = sub.add_parser(
        'chunk', help='List parsed segments (chunks) of a document',
    )
    _add_server_arg(chunk)
    _add_dataset_arg(chunk)
    chunk.add_argument('document', help='Document ID')
    chunk.add_argument('--page-size', type=int, default=20)
    chunk.add_argument('--page', type=int, default=None)
    _add_json_arg(chunk)
    chunk.set_defaults(func=cmd_chunk)

    # ---- retrieve ----
    retrieve = sub.add_parser(
        'retrieve', help='Retrieve chunks via lazyllm.Retriever',
    )
    retrieve.add_argument('query', help='Query text')
    retrieve.add_argument(
        '--url', metavar='URL',
        help='Algo service URL (default: from config/env)',
    )
    retrieve.add_argument(
        '--dataset',
        help='Knowledge base / dataset ID to filter on (default: from `lazyrag use`)',
    )
    retrieve.add_argument(
        '--algo-dataset',
        help='Remote algo document name (default: from config/env, usually general_algo)',
    )
    retrieve.add_argument('--group-name', default='block',
                          help='Node group (default: block)')
    retrieve.add_argument('--topk', type=int, default=6,
                          help='Number of results (default: 6)')
    retrieve.add_argument('--similarity', default='cosine',
                          help='Similarity function (default: cosine)')
    retrieve.add_argument('--embed-keys',
                          help='Comma-separated embedding keys')
    retrieve.add_argument(
        '--config', metavar='YAML',
        help='Load retriever configs from runtime_models YAML',
    )
    _add_json_arg(retrieve)
    retrieve.set_defaults(func=cmd_retrieve)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ApiError as exc:
        print(f'API error ({exc.status_code}): {exc}', file=sys.stderr)
        if exc.payload:
            # Diagnostics go to stderr so scripts consuming stdout are
            # not polluted with error-path JSON.
            import json as _json
            print(
                _json.dumps(exc.payload, ensure_ascii=False, indent=2),
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        print('\nAborted.', file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f'Error: {exc}', file=sys.stderr)
        return 1
