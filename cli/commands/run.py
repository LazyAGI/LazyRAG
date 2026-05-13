"""Run lifecycle commands: run-list, run-undo."""

import argparse
import sys
import time
from typing import Any, Dict, List
from urllib.parse import quote

from cli import upload_state
from cli.client import ApiError, auth_request, print_json
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset


# ---------------------------------------------------------------------------
# run-list
# ---------------------------------------------------------------------------

def _format_time(ts):
    if not ts:
        return '-'
    try:
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(ts)))
    except (TypeError, ValueError):
        return str(ts)


def cmd_run_list(args: argparse.Namespace) -> int:
    if args.all_datasets:
        runs = upload_state.list_runs(None)
    else:
        try:
            dataset_id = resolve_dataset(args.dataset)
        except SystemExit:
            # no dataset set and no --dataset → fall back to all
            runs = upload_state.list_runs(None)
        else:
            runs = upload_state.list_runs(dataset_id)

    if args.as_json:
        print_json(runs)
        return 0

    if not runs:
        print('No runs found.')
        return 0

    print(f'{"run_id":<40} {"status":<12} {"uploaded":<9} '
          f'{"failed":<7} {"created_at":<20} {"dataset"}')
    print('-' * 110)
    for r in runs:
        print(
            f'{r["run_id"]:<40} {r["status"]:<12} '
            f'{r["uploaded_count"]:<9} {r["failed_count"]:<7} '
            f'{_format_time(r["created_at"]):<20} '
            f'{r.get("dataset_id") or "-"}'
        )
    return 0


# ---------------------------------------------------------------------------
# run-undo
# ---------------------------------------------------------------------------

def cmd_run_undo(args: argparse.Namespace) -> int:
    try:
        run_dir = upload_state.load_run(args.run_id)
    except FileNotFoundError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

    manifest = upload_state.read_manifest(run_dir)
    state = upload_state.read_state(run_dir)
    dataset_id = manifest.get('dataset_id')
    # Route the undo back to the server where the run was created so we
    # don't accidentally delete documents in another environment that
    # happens to share the dataset ID.
    manifest_server = manifest.get('server_url')
    if manifest_server:
        if args.server and args.server.rstrip('/') != manifest_server.rstrip('/'):
            print(
                f'warn: ignoring --server {args.server} — run was created '
                f'against {manifest_server}; continuing with the original '
                'server',
                file=sys.stderr,
            )
        args.server = manifest_server
    uploaded = state.get('uploaded', {}) or {}
    # Failed entries can also carry a document_id if batchUpload succeeded
    # but start/parse failed — those servers-side orphans need cleanup too.
    failed_with_doc = {
        rel: info
        for rel, info in (state.get('failed', {}) or {}).items()
        if info.get('document_id')
    }
    targets: Dict[str, Dict[str, Any]] = {}
    targets.update(uploaded)
    targets.update(failed_with_doc)

    if not targets:
        print(f'Run {args.run_id} has no uploaded documents to undo.')
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            print(
                'Error: use -y to confirm undo in non-interactive mode',
                file=sys.stderr,
            )
            return 1
        answer = input(
            f'Delete {len(targets)} document(s) from dataset '
            f'{dataset_id!r} (run {args.run_id})? [y/N] '
        )
        if answer.strip().lower() not in ('y', 'yes'):
            print('Aborted.', file=sys.stderr)
            return 1

    deleted: List[str] = []
    errors: List[Dict[str, Any]] = []

    # Only prune index entries that still belong to *this* run — a later run
    # may have re-uploaded the same relative_path and overwritten the index,
    # and removing that entry here would hide the newer document from dedup.
    current_index = upload_state.load_index(dataset_id, args.server) if dataset_id else {}
    run_id = manifest.get('run_id') or run_dir.name

    # Track which buckets an entry came from so we can scrub the persisted
    # state after a successful delete — otherwise a partial-failure rerun
    # would re-issue DELETE for already-deleted docs and see 404.
    uploaded_keys = set(uploaded.keys())
    failed_keys = set(failed_with_doc.keys())

    for rel_path, info in list(targets.items()):
        doc_id = info.get('document_id')
        if not doc_id:
            errors.append({'path': rel_path, 'error': 'no document_id'})
            continue
        try:
            auth_request(
                'DELETE',
                f'{CORE_API_PREFIX}/datasets/{quote(str(dataset_id), safe="")}'
                f'/documents/{quote(str(doc_id), safe="")}',
                server=args.server,
            )
            deleted.append(rel_path)
            # Persist progress incrementally so re-running run-undo after a
            # transient partial failure picks up where we left off.
            state = upload_state.read_state(run_dir)
            if rel_path in uploaded_keys:
                state.get('uploaded', {}).pop(rel_path, None)
            if rel_path in failed_keys:
                state.get('failed', {}).pop(rel_path, None)
            upload_state.write_state(run_dir, state)
            idx_entry = current_index.get(rel_path)
            if idx_entry is None:
                continue
            # Index is keyed by rel_path, but each entry remembers the run
            # and document that wrote it; only drop if those still match
            # what we just deleted.
            entry_run = idx_entry.get('run_id')
            entry_doc = idx_entry.get('document_id')
            if entry_doc == doc_id or (entry_run and entry_run == run_id):
                upload_state.remove_from_index(dataset_id, rel_path, args.server)
        except ApiError as exc:
            errors.append({
                'path': rel_path, 'document_id': doc_id, 'error': str(exc),
            })

    # Only flip status to `undone` once everything is cleaned; otherwise
    # leave it in an intermediate state so the user is pushed to resolve
    # the remaining errors rather than re-running blind.
    if not errors:
        upload_state.update_state(run_dir, status='undone')
    else:
        upload_state.update_state(run_dir, status='undone_partial')

    if args.as_json:
        print_json({
            'run_id': args.run_id,
            'dataset_id': dataset_id,
            'deleted_count': len(deleted),
            'error_count': len(errors),
            'errors': errors,
        })
    else:
        print(
            f'Undo complete: deleted={len(deleted)} errors={len(errors)}'
        )
        for err in errors:
            print(f'  ! {err.get("path")}: {err.get("error")}',
                  file=sys.stderr)

    return 0 if not errors else 1
