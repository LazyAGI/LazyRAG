"""Upload command: stateful batch import with dedup, resume, and retry."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote, urlencode

from cli import upload_state
from cli.client import ApiError, auth_request, auth_upload, print_json, resolve_server_url
from cli.config import CORE_API_PREFIX
from cli.context import resolve_dataset

RUNNING_TASK_STATES = {'CREATING', 'RUNNING', 'QUEUED', 'WAITING', 'WORKING'}
SUCCESS_TASK_STATES = {'SUCCESS', 'SUCCEEDED'}


# ---------------------------------------------------------------------------
# file collection
# ---------------------------------------------------------------------------

def parse_extensions(raw: Optional[str]) -> Optional[Set[str]]:
    if not raw:
        return None
    items: Set[str] = set()
    for item in raw.split(','):
        normalized = item.strip().lower().lstrip('.')
        if normalized:
            items.add(normalized)
    return items or None


def collect_files(
    directory: str,
    recursive: bool = True,
    include_hidden: bool = False,
    extensions: Optional[Set[str]] = None,
) -> List[Tuple[str, str]]:
    """Scan *directory* and return ``(absolute_path, relative_path)`` pairs."""
    root = Path(directory).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f'directory not found: {root}')
    if not root.is_dir():
        raise NotADirectoryError(f'not a directory: {root}')

    entries: List[Tuple[str, str]] = []
    iterator = root.rglob('*') if recursive else root.iterdir()
    for p in sorted(iterator):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = [seg for seg in rel.split('/') if seg]
        if not include_hidden and any(seg.startswith('.') for seg in parts):
            continue
        suffix = p.suffix.lower().lstrip('.')
        if extensions is not None and suffix not in extensions:
            continue
        entries.append((str(p), rel))
    return entries


# ---------------------------------------------------------------------------
# low-level server operations
# ---------------------------------------------------------------------------

def upload_single_file(
    dataset_id: str,
    source_path: str,
    relative_path: str,
    server: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Upload one file using the batchUpload endpoint."""
    filename = Path(relative_path).name
    fields: Dict[str, str] = {}
    if relative_path != filename:
        fields['relative_path'] = relative_path

    path = f'{CORE_API_PREFIX}/datasets/{dataset_id}/tasks:batchUpload'
    data = auth_upload(
        path=path,
        fields=fields,
        file_field='files',
        filename=filename,
        source_path=source_path,
        server=server,
        timeout=timeout,
    )
    tasks = data.get('tasks') or []
    if not tasks:
        raise RuntimeError(f'No task created for {source_path}')
    return tasks[0]


def start_tasks(
    dataset_id: str,
    task_ids: Sequence[str],
    server: Optional[str] = None,
) -> Dict[str, Any]:
    path = f'{CORE_API_PREFIX}/datasets/{dataset_id}/tasks:start'
    return auth_request(
        'POST', path, server=server,
        payload={'task_ids': list(task_ids)},
    )


def get_task(
    dataset_id: str,
    task_id: str,
    server: Optional[str] = None,
) -> Dict[str, Any]:
    path = (
        f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}'
        f'/tasks/{quote(task_id, safe="")}'
    )
    data = auth_request('GET', path, server=server)
    return data.get('data', data)


def wait_for_tasks(
    dataset_id: str,
    task_ids: Sequence[str],
    interval: float = 3.0,
    timeout: float = 0.0,
    server: Optional[str] = None,
    on_finish: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """Poll tasks until they leave a running state.

    If *on_finish* callback is provided, called with (task_id, task) each time
    a task transitions to terminal state (so caller can persist progress).
    """
    remaining = set(task_ids)
    last_state: Dict[str, str] = {}
    finished: Dict[str, Dict[str, Any]] = {}
    deadline = time.time() + timeout if timeout > 0 else None

    while remaining:
        for tid in list(remaining):
            try:
                task = get_task(dataset_id, tid, server=server)
            except (ApiError, OSError, RuntimeError) as exc:
                # OSError/URLError covers transient network failures;
                # swallow and retry on the next poll so a flaky network
                # doesn't abort the whole --wait loop.
                print(f'  task {tid}: error fetching status ({exc})',
                      file=sys.stderr)
                continue
            state = task.get('task_state') or 'UNKNOWN'
            if last_state.get(tid) != state:
                # Progress lines are sent to stderr so callers that parse
                # --json output from stdout aren't disrupted by wait logs.
                print(f'  task {tid}: {state}', file=sys.stderr)
                last_state[tid] = state
            if state not in RUNNING_TASK_STATES:
                finished[tid] = task
                remaining.discard(tid)
                if on_finish is not None:
                    try:
                        on_finish(tid, task)
                    except Exception:  # noqa: BLE001
                        pass

        if not remaining:
            break
        if deadline is not None:
            now = time.time()
            if now >= deadline:
                raise TimeoutError(
                    f'Timed out waiting for tasks: {sorted(remaining)}',
                )
            # Cap the sleep so we never blow past the deadline by up to a
            # full polling interval.
            time.sleep(min(interval, deadline - now))
        else:
            time.sleep(interval)

    return finished


# ---------------------------------------------------------------------------
# remote doc listing (paginated)
# ---------------------------------------------------------------------------

def _load_remote_docs(
    dataset_id: str,
    server: Optional[str] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch all documents in a dataset, paging through.

    Uses the backend's ``page_token`` cursor (the core service ignores
    ``page``) and raises on API errors so callers can tell "remote listing
    failed" apart from "dataset is empty" — swallowing the error here would
    silently classify every local file as new and re-upload duplicates.
    """
    docs: List[Dict[str, Any]] = []
    page_token = ''
    for _ in range(1000):  # safety
        params: Dict[str, str] = {'page_size': str(page_size)}
        if page_token:
            params['page_token'] = page_token
        query = urlencode(params)
        path = (
            f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}'
            f'/documents?{query}'
        )
        data = auth_request('GET', path, server=server)
        body = data.get('data', data)
        batch = body.get('documents', body.get('list', []))
        if not batch:
            break
        docs.extend(batch)
        page_token = (
            body.get('next_page_token')
            or body.get('nextPageToken')
            or ''
        )
        if not page_token:
            break
    return docs


# ---------------------------------------------------------------------------
# source selection: --dir / --resume / --retry-failed
# ---------------------------------------------------------------------------

def _source_from_dir(args: argparse.Namespace, dataset_id: str) -> Tuple[Path, Dict[str, Any]]:
    """Build a new run from a fresh directory scan."""
    extensions = parse_extensions(args.extensions)
    entries = collect_files(
        directory=args.directory,
        recursive=args.recursive,
        include_hidden=args.include_hidden,
        extensions=extensions,
    )
    if args.limit:
        entries = entries[:args.limit]

    root = str(Path(args.directory).expanduser().resolve())
    files = upload_state.scan_to_files(root, entries)

    run_id, run_dir = upload_state.new_run(dataset_id)
    manifest = {
        'run_id': run_id,
        'dataset_id': dataset_id,
        # Pin the server at creation time so `--resume`/`--retry-failed`/
        # `run-undo` can talk back to the same environment even if the
        # user later switches credentials or passes a different --server.
        'server_url': resolve_server_url(args.server),
        'root_dir': root,
        'created_at': int(time.time()),
        'files': files,
    }
    upload_state.write_manifest(run_dir, manifest)
    upload_state.write_state(run_dir, {
        'status': 'running',
        'pending': [f['relative_path'] for f in files],
        'uploaded': {},
        'skipped': {},
        'failed': {},
        'started_tasks': [],
        'finished_tasks': {},
    })
    return run_dir, manifest


def _source_from_resume(args: argparse.Namespace) -> Tuple[Path, Dict[str, Any]]:
    """Load an existing run for resume."""
    run_dir = upload_state.load_run(args.resume)
    manifest = upload_state.read_manifest(run_dir)
    return run_dir, manifest


def _source_from_retry_failed(args: argparse.Namespace, dataset_id: str) -> Tuple[Path, Dict[str, Any]]:
    """Pick up failed items from the latest run of this dataset.

    Walks backwards through runs (skipping setup-error / empty-failed
    ones) so a transient error during dedup in a newer run can't mask
    retriable failures recorded in the previous run.
    """
    latest = upload_state.latest_run(dataset_id, with_failed_only=True)
    if latest is None:
        raise RuntimeError(
            f'No failed run found for dataset {dataset_id!r} '
            'to retry failures from.',
        )
    old_manifest = upload_state.read_manifest(latest)
    old_state = upload_state.read_state(latest)
    failed = old_state.get('failed', {})
    if not failed:
        raise RuntimeError(
            f'No failed items in latest run ({latest.name}); nothing to retry.',
        )

    # Build a new manifest containing only failed files, re-stating each so
    # edits made between the original run and the retry (the normal recovery
    # path) are picked up and recorded in the cross-run index.  Carry over
    # any ``document_id`` left behind by a failed run (batchUpload created
    # the doc; start/parse blew up afterwards) so the retry path can delete
    # that orphan before uploading a fresh copy, instead of duplicating.
    old_files_by_path = {
        f['relative_path']: f for f in old_manifest.get('files', [])
    }
    retry_files: List[Dict[str, Any]] = []
    for rel_path, failed_info in failed.items():
        old = old_files_by_path.get(rel_path)
        if old is None:
            continue
        abs_path = old.get('abs_path')
        try:
            st = Path(abs_path).stat() if abs_path else None
        except OSError:
            st = None
        orphan_doc = failed_info.get('document_id') if isinstance(failed_info, dict) else None
        entry: Dict[str, Any]
        if st is not None:
            entry = {
                'relative_path': rel_path,
                'abs_path': abs_path,
                'size': st.st_size,
                'mtime': int(st.st_mtime),
            }
        else:
            # File is gone since the original run — keep the old entry so the
            # upload attempt surfaces the missing-file error, rather than
            # silently dropping it.
            entry = dict(old)
        if orphan_doc:
            entry['remote_document_id'] = orphan_doc
        retry_files.append(entry)

    run_id, run_dir = upload_state.new_run(dataset_id)
    manifest = {
        'run_id': run_id,
        'dataset_id': dataset_id,
        # Inherit the server from the previous run when the old manifest
        # recorded one; otherwise pin the current server.
        'server_url': (
            old_manifest.get('server_url')
            or resolve_server_url(args.server)
        ),
        'root_dir': old_manifest.get('root_dir'),
        'created_at': int(time.time()),
        'retry_of': latest.name,
        'files': retry_files,
    }
    upload_state.write_manifest(run_dir, manifest)
    upload_state.write_state(run_dir, {
        'status': 'running',
        'pending': [f['relative_path'] for f in retry_files],
        'uploaded': {},
        'skipped': {},
        'failed': {},
        'started_tasks': [],
        'finished_tasks': {},
    })
    return run_dir, manifest


# ---------------------------------------------------------------------------
# core upload loop (reused by all modes)
# ---------------------------------------------------------------------------

def _files_to_upload(
    run_dir: Path,
    manifest: Dict[str, Any],
    dataset_id: str,
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, List[Dict[str, Any]]]]]:
    """Given a manifest + existing state, decide which files to upload.

    Returns: (files_to_process, categories).
    """
    state = upload_state.read_state(run_dir)
    all_files: List[Dict[str, Any]] = manifest.get('files', [])

    # Filter: skip files already uploaded/skipped in prior pass.
    done = set(state.get('uploaded', {}).keys())
    done |= set(state.get('skipped', {}).keys())
    # On --resume, *also* retry previously failed items — the user asked
    # to pick up where Ctrl-C (or a transient error) left off, and any
    # failures recorded prior are by definition not yet complete.  We
    # clear them from state['failed'] so they go back into the normal
    # upload loop with the same pending-carry-forward path as fresh
    # files, but we:
    #   - re-stat each file so edits the user made before resuming are
    #     reflected in the persisted size/mtime, and
    #   - carry any server-side ``document_id`` forward as
    #     ``remote_document_id`` so the upload loop can delete the orphan
    #     first (otherwise we'd duplicate the document remotely).
    # --retry-failed and --dir intentionally keep the old semantics
    # (don't re-attempt previous failures in-place).
    resume_orphans: Dict[str, str] = {}
    if args.resume:
        prior_failed = state.get('failed', {}) or {}
        if prior_failed:
            for rel, info in prior_failed.items():
                if isinstance(info, dict):
                    doc_id = info.get('document_id')
                    if doc_id:
                        resume_orphans[rel] = doc_id
            cleared = dict(state)
            cleared['failed'] = {}
            upload_state.write_state(run_dir, cleared)
    pending: List[Dict[str, Any]] = []
    for f in all_files:
        rel = f['relative_path']
        if rel in done:
            continue
        entry = f
        if args.resume:
            try:
                st = Path(f['abs_path']).stat()
            except OSError:
                st = None
            if st is not None and (
                st.st_size != f.get('size') or int(st.st_mtime) != f.get('mtime')
            ):
                entry = {**f, 'size': st.st_size, 'mtime': int(st.st_mtime)}
        orphan = resume_orphans.get(rel)
        if orphan:
            entry = {**entry, 'remote_document_id': orphan}
        pending.append(entry)

    # Dedup classification (only for --dir mode, not for resume/retry-failed)
    categories = {'new': [], 'changed': [], 'existing': []}
    if args.directory:
        remote_docs = _load_remote_docs(dataset_id, server=args.server)
        index = upload_state.load_index(dataset_id, args.server)
        categories = upload_state.classify_files(pending, remote_docs, index)

        to_process: List[Dict[str, Any]] = list(categories['new'])

        if args.replace_changed:
            # Delete remote doc before upload so batchUpload creates fresh one.
            replaceable: List[Dict[str, Any]] = []
            for f in categories['changed']:
                doc_id = f.get('remote_document_id')
                if doc_id:
                    try:
                        auth_request(
                            'DELETE',
                            f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}'
                            f'/documents/{quote(str(doc_id), safe="")}',
                            server=args.server,
                        )
                        upload_state.remove_from_index(
                            dataset_id, f['relative_path'], args.server,
                        )
                    except ApiError as exc:
                        # If the old doc cannot be deleted, re-uploading
                        # would leave two documents for the same rel_path
                        # and confuse later dedup; record the failure and
                        # skip this file instead.
                        print(
                            f'  warn: failed to delete old doc {doc_id}: {exc}',
                            file=sys.stderr,
                        )
                        upload_state.update_state(
                            run_dir,
                            failed={f['relative_path']: {
                                'error': f'delete old doc {doc_id} failed: {exc}',
                                'phase': 'replace',
                            }},
                        )
                        continue
                replaceable.append(f)
            to_process.extend(replaceable)
        elif categories['changed']:
            print(
                f'Warning: {len(categories["changed"])} file(s) changed since '
                'last upload. Use --replace-changed to update them.',
                file=sys.stderr,
            )
            for f in categories['changed']:
                upload_state.update_state(
                    run_dir,
                    skipped={f['relative_path']: 'changed_needs_replace'},
                )

        # Existing files are always skipped (they're identical remote<>local).
        for f in categories['existing']:
            upload_state.update_state(
                run_dir,
                skipped={f['relative_path']: 'existing'},
            )

        return to_process, categories

    # Resume / retry-failed: no dedup, process everything still pending
    return pending, categories


def _mark_failed(
    run_dir: Path,
    rel_path: str,
    error: str,
    phase: str,
) -> None:
    """Move a file from uploaded → failed. Used for start/parse failures.

    Preserves the ``document_id`` / ``task_id`` / ``size`` / ``mtime`` from
    the pre-failure uploaded entry so ``run-undo`` can still clean up the
    orphan document the server already created.
    """
    state = upload_state.read_state(run_dir)
    prior = state.setdefault('uploaded', {}).pop(rel_path, None) or {}
    entry: Dict[str, Any] = {'error': error, 'phase': phase}
    for key in ('document_id', 'task_id', 'size', 'mtime'):
        if key in prior:
            entry[key] = prior[key]
    state.setdefault('failed', {})[rel_path] = entry
    upload_state.write_state(run_dir, state)


def _run_upload_loop(
    run_dir: Path,
    manifest: Dict[str, Any],
    files: List[Dict[str, Any]],
    dataset_id: str,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Upload files sequentially, persisting state after each.

    Note: cross-run `uploaded.json` index is NOT written here. It is only
    written after a task is confirmed SUCCESS (in cmd_upload's on_finish).
    """
    # In --json mode, progress lines go to stderr so stdout remains pure JSON.
    _out = sys.stderr if getattr(args, 'as_json', False) else sys.stdout
    total = len(files)
    if total == 0:
        print('No files to upload.', file=_out)
        return {
            'uploaded_count': 0, 'failed_count': 0,
            'task_ids': [], 'task_to_rel': {},
        }

    print(f'Uploading {total} file(s) to dataset={dataset_id}', file=_out)
    task_ids: List[str] = []
    # Map task_id → rel_path so later phases can attribute failures.
    task_to_rel: Dict[str, str] = {}

    for idx, f in enumerate(files, 1):
        rel = f['relative_path']
        src = f['abs_path']
        # If this entry carries a stale remote_document_id (e.g. from
        # --retry-failed picking up an orphan doc that start/parse never
        # cleaned up), delete the old document first so the server-side
        # batchUpload doesn't leave behind duplicates for the same path.
        orphan_doc = f.get('remote_document_id')
        if orphan_doc:
            try:
                auth_request(
                    'DELETE',
                    f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}'
                    f'/documents/{quote(str(orphan_doc), safe="")}',
                    server=args.server,
                )
                upload_state.remove_from_index(dataset_id, rel, args.server)
            except ApiError as exc:
                # 404 means the orphan is already gone — proceed with
                # upload.  Any other error leaves a live duplicate on the
                # server, so we must skip and surface a failure rather
                # than silently create a second document.
                if exc.status_code == 404:
                    upload_state.remove_from_index(dataset_id, rel, args.server)
                else:
                    upload_state.update_state(
                        run_dir,
                        failed={rel: {
                            'error': (
                                f'delete orphan doc {orphan_doc} failed: {exc}'
                            ),
                            'phase': 'retry-cleanup',
                            'document_id': orphan_doc,
                        }},
                    )
                    print(
                        f'  [{idx}/{total}] {rel} -> skipped (orphan delete'
                        f' failed: {exc})',
                        file=sys.stderr,
                    )
                    continue
        try:
            task = upload_single_file(
                dataset_id, src, rel,
                server=args.server, timeout=args.timeout,
            )
            task_id = task.get('task_id', '')
            state_str = task.get('task_state', '')
            document_id = task.get('document_id', '')
            # batchUpload's contract only guarantees task_state; drop empty
            # task_ids so we don't poison `tasks:start` with a blank id
            # that the backend would reject.
            if task_id:
                task_ids.append(task_id)
                task_to_rel[task_id] = rel
            upload_state.update_state(
                run_dir,
                uploaded={rel: {
                    'task_id': task_id,
                    'document_id': document_id,
                    'size': f['size'],
                    'mtime': f['mtime'],
                    'verified': False,  # flipped to True after SUCCESS
                }},
            )
            print(
                f'  [{idx}/{total}] {rel} -> task={task_id} state={state_str}',
                file=_out,
            )
        except Exception as exc:  # noqa: BLE001
            upload_state.update_state(
                run_dir,
                failed={rel: {'error': str(exc), 'phase': 'upload'}},
            )
            print(f'  [{idx}/{total}] {rel} -> ERROR: {exc}', file=sys.stderr)

    state = upload_state.read_state(run_dir)
    return {
        'uploaded_count': len(state.get('uploaded', {})),
        'failed_count': len(state.get('failed', {})),
        'task_ids': task_ids,
        'task_to_rel': task_to_rel,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_upload(args: argparse.Namespace) -> int:
    # Mode selection — exactly one of --dir, --resume, --retry-failed
    mode_count = bool(args.directory) + bool(args.resume) + bool(args.retry_failed)
    if mode_count == 0:
        print(
            'Error: one of --dir, --resume, --retry-failed is required',
            file=sys.stderr,
        )
        return 1
    if mode_count > 1:
        print(
            'Error: --dir, --resume, --retry-failed are mutually exclusive',
            file=sys.stderr,
        )
        return 1

    # Dataset only needed for --dir / --retry-failed;
    # --resume reads from the run's manifest.  Wrap setup so that recovery
    # flows (`--retry-failed` with no prior run, `--resume` with a bad run
    # id, etc.) surface as a friendly error + non-zero exit rather than a
    # Python traceback crashing out of main().
    try:
        if args.resume:
            run_dir, manifest = _source_from_resume(args)
            dataset_id = manifest.get('dataset_id')
            if not dataset_id:
                print('Error: resumed manifest has no dataset_id',
                      file=sys.stderr)
                return 1
        else:
            dataset_id = resolve_dataset(args.dataset)
            if args.retry_failed:
                run_dir, manifest = _source_from_retry_failed(args, dataset_id)
            else:
                run_dir, manifest = _source_from_dir(args, dataset_id)
    except (FileNotFoundError, NotADirectoryError, RuntimeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

    # Recovery flows (resume / retry-failed) must talk to the server where
    # the run was originally created; otherwise dataset IDs that happen to
    # exist in another environment (staging vs prod) would replay uploads
    # or undo documents against the wrong server.  Pin args.server to the
    # manifest's server_url, warning only when the user explicitly asked
    # for a different --server.
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

    as_json = getattr(args, 'as_json', False)
    # In --json mode, progress / dedup lines would poison the JSON blob we
    # emit at the end; send them to stderr so stdout is parseable.
    def _info(msg: str) -> None:
        print(msg, file=sys.stderr if as_json else sys.stdout)

    _info(f'Run: {manifest.get("run_id")}  dir: {run_dir}')

    try:
        files_to_process, categories = _files_to_upload(
            run_dir, manifest, dataset_id, args,
        )

        if categories.get('existing') or categories.get('changed'):
            _info(
                f'Dedup: new={len(categories.get("new", []))} '
                f'changed={len(categories.get("changed", []))} '
                f'existing={len(categories.get("existing", []))}'
            )

        upload_result = _run_upload_loop(
            run_dir, manifest, files_to_process, dataset_id, args,
        )
        task_to_rel: Dict[str, str] = upload_result['task_to_rel']
        # Build rel → file info map for the cross-run index write on success.
        rel_to_file = {f['relative_path']: f for f in files_to_process}

        # On --resume, re-integrate tasks that were created by a prior
        # invocation but not yet verified.  Tasks already in
        # state['started_tasks'] go *straight to the wait set* — calling
        # tasks:start on them again is not idempotent and can fail the
        # whole batch — while tasks that were uploaded but never started
        # are appended to task_ids so the normal start/wait path runs for
        # them.
        task_ids = list(upload_result['task_ids'])
        resume_already_started: List[str] = []
        if args.resume:
            saved_state = upload_state.read_state(run_dir)
            saved_uploaded = saved_state.get('uploaded', {})
            prior_started_set = set(
                saved_state.get('started_tasks', []) or []
            )
            prior_finished_set = set(
                (saved_state.get('finished_tasks', {}) or {}).keys()
            )
            manifest_files_by_rel = {
                f['relative_path']: f for f in manifest.get('files', [])
            }
            for rel, info in saved_uploaded.items():
                if info.get('verified'):
                    continue
                tid = info.get('task_id') or ''
                if not tid:
                    continue
                if rel not in rel_to_file and rel in manifest_files_by_rel:
                    rel_to_file[rel] = manifest_files_by_rel[rel]
                task_to_rel[tid] = rel
                if tid in prior_started_set and tid not in prior_finished_set:
                    # Already started previously; skip re-start, wait directly.
                    if tid not in resume_already_started:
                        resume_already_started.append(tid)
                elif tid not in task_ids and tid not in prior_started_set:
                    task_ids.append(tid)

        started_task_ids: List[str] = []
        start_failed = False
        if task_ids:
            _info(f'Starting {len(task_ids)} task(s)...')
            try:
                resp = start_tasks(dataset_id, task_ids, server=args.server)
                started = resp.get('started_count', 0)
                failed_count = resp.get('failed_count', 0)
                _info(f'  started={started} failed={failed_count}')
                for t in (resp.get('tasks') or []):
                    tid = t.get('task_id', '')
                    if t.get('status') == 'STARTED':
                        started_task_ids.append(tid)
                    else:
                        # Task failed to start — attribute to rel_path.
                        rel = task_to_rel.get(tid)
                        if rel:
                            _mark_failed(
                                run_dir, rel,
                                t.get('message') or t.get('status')
                                or 'task failed to start',
                                'start',
                            )
                if failed_count > 0:
                    start_failed = True
                # update_state replaces scalar/list values, so we must union
                # with whatever started_tasks the persisted state already
                # holds from earlier runs (otherwise a resume that starts
                # some fresh tasks would forget the originals and try to
                # re-start them next time — tasks:start is not idempotent).
                prior_started_list = (
                    upload_state.read_state(run_dir).get('started_tasks') or []
                )
                merged_started = list(prior_started_list)
                for tid in started_task_ids:
                    if tid and tid not in merged_started:
                        merged_started.append(tid)
                if resume_already_started:
                    for tid in resume_already_started:
                        if tid and tid not in merged_started:
                            merged_started.append(tid)
                upload_state.update_state(
                    run_dir, started_tasks=merged_started,
                )
            except (ApiError, RuntimeError) as exc:
                print(f'  Error: start request failed ({exc})', file=sys.stderr)
                start_failed = True
                # The whole batch failed to start — attribute all uploaded to failed.
                for tid in task_ids:
                    rel = task_to_rel.get(tid)
                    if rel:
                        _mark_failed(run_dir, rel, str(exc), 'start')

        # optional wait
        wait_failures = 0
        if args.wait and args.resume:
            # Fold in prior-run started-but-not-finished tasks we collected
            # above, plus any others recorded in state['started_tasks'] that
            # didn't surface through state['uploaded'] (defensive).
            for tid in resume_already_started:
                if tid and tid not in started_task_ids:
                    started_task_ids.append(tid)
            saved_state = upload_state.read_state(run_dir)
            prior_started = saved_state.get('started_tasks', []) or []
            prior_finished = set(
                (saved_state.get('finished_tasks', {}) or {}).keys(),
            )
            for tid in prior_started:
                if tid and tid not in prior_finished and tid not in started_task_ids:
                    started_task_ids.append(tid)
        if args.wait and started_task_ids:
            _info('Waiting for tasks to complete...')

            def _on_finish(tid: str, task: Dict[str, Any]) -> None:
                state_str = task.get('task_state', 'UNKNOWN')
                upload_state.update_state(
                    run_dir,
                    finished_tasks={tid: state_str},
                )
                rel = task_to_rel.get(tid)
                if not rel:
                    return
                if state_str in SUCCESS_TASK_STATES:
                    # Confirmed success: flip verified=True AND record to
                    # cross-run index.
                    state = upload_state.read_state(run_dir)
                    if rel in state.get('uploaded', {}):
                        state['uploaded'][rel]['verified'] = True
                        upload_state.write_state(run_dir, state)
                    f = rel_to_file.get(rel)
                    if f:
                        upload_state.record_upload(dataset_id, rel, {
                            'size': f['size'],
                            'mtime': f['mtime'],
                            'document_id': state.get(
                                'uploaded', {},
                            ).get(rel, {}).get('document_id', ''),
                            'task_id': tid,
                            'run_id': manifest.get('run_id'),
                            'uploaded_at': int(time.time()),
                        }, server_url=args.server)
                else:
                    # Terminal non-success: move to failed.
                    _mark_failed(
                        run_dir, rel,
                        task.get('err_msg') or f'task ended in {state_str}',
                        'wait',
                    )

            finished = wait_for_tasks(
                dataset_id, started_task_ids,
                interval=args.wait_interval,
                timeout=args.wait_timeout,
                server=args.server,
                on_finish=_on_finish,
            )
            failed_tasks = [
                {
                    'task_id': tid,
                    'state': t.get('task_state'),
                    'err_msg': t.get('err_msg'),
                }
                for tid, t in finished.items()
                if t.get('task_state') not in SUCCESS_TASK_STATES
            ]
            wait_failures = len(failed_tasks)
            _info(
                f'Task summary: total={len(finished)} failed={wait_failures}'
            )

        # finalize
        final_state = upload_state.read_state(run_dir)
        status = 'completed'
        if final_state.get('failed') or start_failed or wait_failures:
            status = 'failed'
        upload_state.update_state(run_dir, status=status)

        result = {
            'run_id': manifest.get('run_id'),
            'dataset_id': dataset_id,
            'scanned_count': len(manifest.get('files', [])),
            'upload_count': len(final_state.get('uploaded', {})),
            'skip_count': len(final_state.get('skipped', {})),
            'failed_count': len(final_state.get('failed', {})),
            'task_ids': upload_result['task_ids'],
            'failures': [
                {'path': p, **info}
                for p, info in final_state.get('failed', {}).items()
            ],
            'manifest_path': str(run_dir / 'manifest.json'),
            'status': status,
        }
        upload_state.write_result(run_dir, result)

        if args.report_json:
            try:
                Path(args.report_json).expanduser().write_text(
                    json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8',
                )
            except OSError as exc:
                print(f'  warn: failed to write report: {exc}', file=sys.stderr)

        _info(
            f'Upload done: run={result["run_id"]} '
            f'uploaded={result["upload_count"]} '
            f'skipped={result["skip_count"]} '
            f'failed={result["failed_count"]}'
        )

        if as_json:
            print_json(result)

        return 0 if status == 'completed' else 1

    except KeyboardInterrupt:
        upload_state.update_state(run_dir, status='interrupted')
        print(f'\nInterrupted. Resume with: lazyrag upload --resume {manifest.get("run_id")}',
              file=sys.stderr)
        return 130
    except BaseException as exc:
        # Any other failure (e.g. a transient doc-list API error during
        # dedup) must not leave the run with status='running' — otherwise
        # latest_run() points --retry-failed at a broken run with an empty
        # failed-list, masking the real recovery path.
        upload_state.update_state(
            run_dir,
            status='failed',
            setup_error=str(exc),
        )
        raise


# ---------------------------------------------------------------------------
# task-list / task-get (unchanged semantics)
# ---------------------------------------------------------------------------

def cmd_task_list(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    params = f'?{urlencode({"page_size": str(args.page_size)})}'
    path = (
        f'{CORE_API_PREFIX}/datasets/{quote(dataset_id, safe="")}'
        f'/tasks{params}'
    )
    data = auth_request('GET', path, server=args.server)
    body = data.get('data', data)
    tasks = body.get('tasks') or []

    if args.as_json:
        print_json(tasks)
        return 0
    if not tasks:
        print('No tasks found.')
        return 0
    for t in tasks:
        print(
            f'{t.get("task_id")}  '
            f'state={t.get("task_state")}  '
            f'type={t.get("task_type", "-")}  '
            f'display_name={t.get("display_name", "-")}'
        )
    return 0


def cmd_task_get(args: argparse.Namespace) -> int:
    dataset_id = resolve_dataset(args.dataset)
    task = get_task(dataset_id, args.task_id, server=args.server)
    print_json(task)
    return 0
