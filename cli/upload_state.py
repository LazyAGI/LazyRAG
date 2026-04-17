"""Upload state management: run directories, manifest, state, uploaded index.

Directory layout under ~/.lazyrag/:
  datasets/<dataset_id>/uploaded.json  - cross-run index: relative_path -> entry
  runs/<run_id>/                        - per-run state
    manifest.json                       - directory snapshot
    state.json                          - execution progress (rolling updates)
    result.json                         - final summary
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cli.config import CREDENTIALS_DIR

RUNS_DIR = CREDENTIALS_DIR / 'runs'
DATASETS_DIR = CREDENTIALS_DIR / 'datasets'


# ---------------------------------------------------------------------------
# low-level atomic IO
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically: write to tmp, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    os.replace(tmp, path)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return default


# ---------------------------------------------------------------------------
# run directory management
# ---------------------------------------------------------------------------

_SAFE_DS_CHARS = set(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.'
)


def _sanitize_dataset_id(dataset_id: str) -> str:
    """Reduce a dataset id to filesystem-safe chars for local paths.

    The backend permits slashes and other characters in ``dataset_id``, but
    we use the id as a directory name under ``~/.lazyrag`` — a value like
    ``a/b`` or ``x/../y`` would otherwise create escaping or nested paths.
    Sanitise by replacing unsafe chars with ``_``; to keep collision-free
    with ids that only differ in those unsafe chars (e.g. ``team/a`` vs
    ``team_a``), append a short content-addressed suffix when sanitising
    actually changed the string or when the id starts/ends with a dot.
    """
    if not dataset_id:
        return 'unknown'
    cleaned = ''.join(
        c if c in _SAFE_DS_CHARS else '_' for c in dataset_id
    ).strip('.')
    if not cleaned:
        cleaned = 'unknown'
    if cleaned != dataset_id:
        digest = hashlib.sha256(dataset_id.encode('utf-8')).hexdigest()[:8]
        cleaned = f'{cleaned}-{digest}'
    return cleaned


def _make_run_id(dataset_id: str) -> str:
    # YYYYMMDDTHHMMSS-<ds>
    stamp = time.strftime('%Y%m%dT%H%M%S', time.localtime())
    short_ds = _sanitize_dataset_id(dataset_id)[:16] if dataset_id else 'unknown'
    return f'{stamp}-{short_ds}'


def new_run(dataset_id: str) -> Tuple[str, Path]:
    """Create a fresh run directory. Returns (run_id, dir_path)."""
    run_id = _make_run_id(dataset_id)
    run_dir = RUNS_DIR / run_id
    # Collision-safe (same-second): append counter
    suffix = 1
    while run_dir.exists():
        run_dir = RUNS_DIR / f'{run_id}-{suffix}'
        suffix += 1
    run_dir.mkdir(parents=True)
    run_id = run_dir.name
    return run_id, run_dir


def load_run(run_id_or_path: str) -> Path:
    """Resolve a run identifier or filesystem path to a run directory.

    Accepts:

    - a plain run_id that lives under ``RUNS_DIR``
    - an absolute path to a run dir or its ``manifest.json``
    - a relative path to a run dir or its ``manifest.json`` (so users can
      paste ``./tmp/runs/<run>`` from shell history without the CLI
      silently falling back to a run-id lookup)
    """
    p = Path(run_id_or_path).expanduser()
    # Any path that actually resolves on disk (absolute or relative) wins
    # before we fall back to a run-id lookup.
    if (p.is_absolute() or '/' in run_id_or_path or os.sep in run_id_or_path) and p.exists():
        if p.is_file():  # pointed at manifest.json
            return p.parent
        return p
    # Treat as run_id
    run_dir = RUNS_DIR / run_id_or_path
    if not run_dir.exists():
        raise FileNotFoundError(f'run not found: {run_id_or_path}')
    return run_dir


def latest_run(
    dataset_id: str,
    with_failed_only: bool = False,
) -> Optional[Path]:
    """Find the most recent run directory for a dataset.

    Sorts by the manifest's ``created_at`` rather than the filesystem
    mtime — every later ``update_state`` / ``write_result`` bumps the
    directory's mtime, so mtime can't be trusted to express run age.
    When ``with_failed_only`` is set, setup-error / empty runs that have
    no entries in ``state['failed']`` are skipped so ``--retry-failed``
    can walk back to the previous run that actually has something to
    retry.
    """
    if not RUNS_DIR.exists():
        return None
    candidates: List[Tuple[int, str, Path]] = []
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        manifest = _read_json(run_dir / 'manifest.json', {})
        if manifest.get('dataset_id') != dataset_id:
            continue
        if with_failed_only:
            state = _read_json(run_dir / 'state.json', {}) or {}
            if not state.get('failed'):
                continue
        created_at = manifest.get('created_at') or 0
        # Secondary key: directory name — `new_run()` appends `-1`,
        # `-2`, ... for same-second collisions, so the lexically
        # larger name represents the later run.
        candidates.append((int(created_at), run_dir.name, run_dir))
    if not candidates:
        return None
    candidates.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return candidates[0][2]


def list_runs(dataset_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List runs with summary info, newest first."""
    if not RUNS_DIR.exists():
        return []
    out: List[Dict[str, Any]] = []
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        manifest = _read_json(run_dir / 'manifest.json', {})
        state = _read_json(run_dir / 'state.json', {})
        ds = manifest.get('dataset_id')
        if dataset_id and ds != dataset_id:
            continue
        out.append({
            'run_id': run_dir.name,
            'dataset_id': ds,
            'root_dir': manifest.get('root_dir'),
            'created_at': manifest.get('created_at'),
            'status': state.get('status', 'unknown'),
            'uploaded_count': len(state.get('uploaded', {})),
            'failed_count': len(state.get('failed', {})),
            'skipped_count': len(state.get('skipped', {})),
            'path': str(run_dir),
        })
    out.sort(key=lambda e: e.get('created_at') or 0, reverse=True)
    return out


# ---------------------------------------------------------------------------
# manifest / state / result
# ---------------------------------------------------------------------------

def write_manifest(run_dir: Path, manifest: Dict[str, Any]) -> None:
    _atomic_write_json(run_dir / 'manifest.json', manifest)


def read_manifest(run_dir: Path) -> Dict[str, Any]:
    m = _read_json(run_dir / 'manifest.json', None)
    if m is None:
        raise FileNotFoundError(f'manifest.json missing in {run_dir}')
    return m


def read_state(run_dir: Path) -> Dict[str, Any]:
    return _read_json(run_dir / 'state.json', {}) or {}


def write_state(run_dir: Path, state: Dict[str, Any]) -> None:
    _atomic_write_json(run_dir / 'state.json', state)


def update_state(run_dir: Path, **updates: Any) -> Dict[str, Any]:
    """Read-modify-write state.json. Updates can be scalar or dict-merge."""
    state = read_state(run_dir)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(state.get(key), dict):
            state[key].update(value)
        else:
            state[key] = value
    write_state(run_dir, state)
    return state


def write_result(run_dir: Path, result: Dict[str, Any]) -> None:
    _atomic_write_json(run_dir / 'result.json', result)


def read_result(run_dir: Path) -> Dict[str, Any]:
    return _read_json(run_dir / 'result.json', {}) or {}


# ---------------------------------------------------------------------------
# cross-run uploaded index
# ---------------------------------------------------------------------------

def _server_key(server_url: Optional[str]) -> str:
    """Short stable per-server token for namespacing local state.

    The LazyRAG CLI can be used against multiple deployments; keying
    dedup metadata by dataset_id alone would let uploads in one
    environment poison dedup decisions for another. When a server URL is
    known we prefix the path with a short hash of it; when it's not, we
    fall back to a shared bucket so legacy state written before this
    change is still discoverable.
    """
    if not server_url:
        return ''
    norm = server_url.rstrip('/').lower()
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()[:12]


def index_path(dataset_id: str, server_url: Optional[str] = None) -> Path:
    ds = _sanitize_dataset_id(dataset_id)
    key = _server_key(server_url)
    if key:
        return DATASETS_DIR / key / ds / 'uploaded.json'
    return DATASETS_DIR / ds / 'uploaded.json'


def load_index(
    dataset_id: str,
    server_url: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load the cross-run uploaded index.

    When ``server_url`` is given and the server-scoped file is missing but
    a legacy un-scoped file exists, read that once so upgrades from the
    pre-scoping layout don't silently lose the dedup cache.  We do not
    write back here — ``record_upload`` will populate the scoped file on
    the next successful upload.
    """
    scoped = index_path(dataset_id, server_url)
    if scoped.exists() or not server_url:
        return _read_json(scoped, {}) or {}
    legacy = index_path(dataset_id, None)
    return _read_json(legacy, {}) or {}


def save_index(
    dataset_id: str,
    index: Dict[str, Dict[str, Any]],
    server_url: Optional[str] = None,
) -> None:
    _atomic_write_json(index_path(dataset_id, server_url), index)


def record_upload(
    dataset_id: str,
    relative_path: str,
    entry: Dict[str, Any],
    server_url: Optional[str] = None,
) -> None:
    """Write or update one entry in the uploaded index."""
    index = load_index(dataset_id, server_url)
    index[relative_path] = entry
    save_index(dataset_id, index, server_url)


def remove_from_index(
    dataset_id: str,
    relative_path: str,
    server_url: Optional[str] = None,
) -> None:
    index = load_index(dataset_id, server_url)
    if index.pop(relative_path, None) is not None:
        save_index(dataset_id, index, server_url)


# ---------------------------------------------------------------------------
# directory scan → manifest files
# ---------------------------------------------------------------------------

def scan_to_files(
    root_dir: str,
    entries: List[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    """Turn (abs_path, rel_path) pairs into manifest file dicts with stat."""
    files: List[Dict[str, Any]] = []
    for abs_path, rel_path in entries:
        st = os.stat(abs_path)
        files.append({
            'relative_path': rel_path,
            'abs_path': abs_path,
            'size': st.st_size,
            'mtime': int(st.st_mtime),
        })
    return files


# ---------------------------------------------------------------------------
# dedup classification
# ---------------------------------------------------------------------------

def _is_remote_healthy(doc: Dict[str, Any]) -> bool:
    """Is a remote doc's parse status OK enough to count as 'existing'?

    We conservatively treat unknown status as healthy (server may not expose
    it), and only exclude explicitly failed ones.
    """
    status = (doc.get('status') or doc.get('document_stage') or '').upper()
    if not status:
        return True
    return status not in ('FAILED', 'ERROR', 'CANCELED')


def classify_files(
    local_files: List[Dict[str, Any]],
    remote_docs: List[Dict[str, Any]],
    index: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Classify local files into new / changed / existing.

    - new: remote has no such relative_path at all
    - changed: remote has it but size/mtime differs locally, OR the remote
      doc is in a FAILED/ERROR/CANCELED state (so a plain re-upload would
      duplicate; these must go through the replace-changed path to delete
      the stale doc first)
    - existing: both remote and local index agree the healthy remote doc
      matches the local file
    """
    # Build remote lookup by rel_path; keep *all* remote docs here so we
    # can still see FAILED/ERROR/CANCELED ones and classify them as
    # changed rather than absent — otherwise a re-upload would silently
    # create a second document for the same path.
    remote_by_path: Dict[str, Dict[str, Any]] = {}
    for doc in remote_docs:
        rp = doc.get('rel_path') or doc.get('relative_path')
        if rp:
            remote_by_path[rp] = doc

    new_list: List[Dict[str, Any]] = []
    changed_list: List[Dict[str, Any]] = []
    existing_list: List[Dict[str, Any]] = []

    for f in local_files:
        path = f['relative_path']
        remote = remote_by_path.get(path)
        local_idx = index.get(path)

        if remote is None:
            new_list.append(f)
            continue

        if not _is_remote_healthy(remote):
            # Remote copy is FAILED/ERROR/CANCELED; surface it as a changed
            # file so --replace-changed can clean it up, and the user is
            # warned when --replace-changed is absent.
            changed_list.append({**f, 'remote_document_id': remote.get('document_id')})
            continue

        remote_size = remote.get('document_size') or remote.get('size')
        if remote_size is not None and remote_size != f['size']:
            changed_list.append({**f, 'remote_document_id': remote.get('document_id')})
            continue

        if local_idx is None:
            # Remote has it, but we have no local index mtime to verify.
            # Conservative: treat as existing.
            existing_list.append(f)
            continue

        if local_idx.get('size') != f['size'] or local_idx.get('mtime') != f['mtime']:
            changed_list.append({**f, 'remote_document_id': remote.get('document_id')})
        else:
            existing_list.append(f)

    return {
        'new': new_list,
        'changed': changed_list,
        'existing': existing_list,
    }
