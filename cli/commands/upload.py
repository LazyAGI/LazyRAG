"""Upload command: batch-import a local directory into a dataset."""

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from cli.client import ApiError, auth_request, auth_upload, print_json
from cli.config import CORE_API_PREFIX

RUNNING_TASK_STATES = {'CREATING', 'RUNNING', 'QUEUED', 'WAITING', 'WORKING'}
SUCCESS_TASK_STATES = {'SUCCESS', 'SUCCEEDED'}


# ---------------------------------------------------------------------------
# file collection (reused logic from lazyrag-lite)
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
# upload + task creation via batchUpload
# ---------------------------------------------------------------------------

def upload_single_file(
    dataset_id: str,
    source_path: str,
    relative_path: str,
    server: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Upload one file using the batchUpload endpoint.

    This combines file upload and task creation in a single request.
    Returns the first TaskResponse from the server.
    """
    filename = Path(relative_path).name
    with open(source_path, 'rb') as f:
        content = f.read()

    # The server uses the first path segment of relative_path to create
    # a top-level folder; deeper nesting is NOT reconstructed.  Files
    # from ``sub/deep/file.pdf`` will appear under folder ``sub``.
    fields: Dict[str, str] = {}
    if relative_path != filename:
        fields['relative_path'] = relative_path

    path = f'{CORE_API_PREFIX}/datasets/{dataset_id}/tasks:batchUpload'
    data = auth_upload(
        path=path,
        fields=fields,
        file_field='files',
        filename=filename,
        file_content=content,
        server=server,
        timeout=timeout,
    )
    tasks = data.get('tasks') or []
    if not tasks:
        raise RuntimeError(f'No task created for {source_path}')
    return tasks[0]


# ---------------------------------------------------------------------------
# task start + polling
# ---------------------------------------------------------------------------

def start_tasks(
    dataset_id: str,
    task_ids: Sequence[str],
    server: Optional[str] = None,
) -> Dict[str, Any]:
    """Send POST tasks:start for the given task IDs."""
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
    path = f'{CORE_API_PREFIX}/datasets/{dataset_id}/tasks/{task_id}'
    data = auth_request('GET', path, server=server)
    return data.get('data', data)


def wait_for_tasks(
    dataset_id: str,
    task_ids: Sequence[str],
    interval: float = 3.0,
    timeout: float = 0.0,
    server: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Poll tasks until they leave a running state.  Returns final status map."""
    remaining = set(task_ids)
    last_state: Dict[str, str] = {}
    finished: Dict[str, Dict[str, Any]] = {}
    deadline = time.time() + timeout if timeout > 0 else None

    while remaining:
        for tid in list(remaining):
            try:
                task = get_task(dataset_id, tid, server=server)
            except ApiError as exc:
                print(f'  task {tid}: error fetching status ({exc})',
                      file=sys.stderr)
                continue
            state = task.get('task_state') or 'UNKNOWN'
            if last_state.get(tid) != state:
                print(f'  task {tid}: {state}')
                last_state[tid] = state
            if state not in RUNNING_TASK_STATES:
                finished[tid] = task
                remaining.discard(tid)

        if not remaining:
            break
        if deadline is not None and time.time() >= deadline:
            raise TimeoutError(
                f'Timed out waiting for tasks: {sorted(remaining)}',
            )
        time.sleep(interval)

    return finished


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_upload(args: argparse.Namespace) -> int:
    dataset_id = args.dataset

    extensions = parse_extensions(args.extensions)
    file_entries = collect_files(
        directory=args.directory,
        recursive=args.recursive,
        include_hidden=args.include_hidden,
        extensions=extensions,
    )
    if args.limit:
        file_entries = file_entries[:args.limit]

    if not file_entries:
        print('No files matched.')
        return 0

    total = len(file_entries)
    print(f'Found {total} file(s), uploading to dataset={dataset_id}')

    task_ids: List[str] = []
    failures: List[Dict[str, Any]] = []
    successes = 0

    for idx, (src, rel) in enumerate(file_entries, 1):
        try:
            task = upload_single_file(
                dataset_id, src, rel,
                server=args.server, timeout=args.timeout,
            )
            task_id = task.get('task_id', '')
            state = task.get('task_state', '')
            if task_id:
                task_ids.append(task_id)
            successes += 1
            print(f'  [{idx}/{total}] {rel} -> task={task_id} state={state}')
        except Exception as exc:  # noqa: BLE001
            failures.append({'path': rel, 'error': str(exc)})
            print(f'  [{idx}/{total}] {rel} -> ERROR: {exc}', file=sys.stderr)

    print(f'Upload summary: success={successes} failed={len(failures)}')
    if failures:
        print_json({'failures': failures})

    # start tasks
    start_failed = False
    started_task_ids: List[str] = []
    if task_ids:
        print(f'Starting {len(task_ids)} task(s)...')
        try:
            resp = start_tasks(dataset_id, task_ids, server=args.server)
            started = resp.get('started_count', 0)
            failed_count = resp.get('failed_count', 0)
            print(f'  started={started} failed={failed_count}')
            # collect only successfully started task IDs
            for t in (resp.get('tasks') or []):
                if t.get('status') == 'STARTED':
                    started_task_ids.append(t.get('task_id', ''))
            if failed_count > 0:
                start_failed = True
        except (ApiError, RuntimeError) as exc:
            print(f'  Error: start request failed ({exc})', file=sys.stderr)
            start_failed = True

    # optional wait — only poll tasks that were actually started
    wait_ids = [tid for tid in started_task_ids if tid]
    if args.wait and wait_ids:
        print('Waiting for tasks to complete...')
        finished = wait_for_tasks(
            dataset_id, wait_ids,
            interval=args.wait_interval,
            timeout=args.wait_timeout,
            server=args.server,
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
        print(
            f'Task summary: total={len(finished)} '
            f'failed={len(failed_tasks)}'
        )
        if failed_tasks:
            print_json({'task_failures': failed_tasks})
            return 1

    return 1 if (failures or start_failed) else 0


def cmd_task_list(args: argparse.Namespace) -> int:
    params = f'?page_size={args.page_size}'
    path = f'{CORE_API_PREFIX}/datasets/{args.dataset}/tasks{params}'
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
    task = get_task(args.dataset, args.task_id, server=args.server)
    print_json(task)
    return 0
