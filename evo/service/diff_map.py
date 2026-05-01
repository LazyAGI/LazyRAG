from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from evo.apply.git_workspace import FileDiff, GitWorkspace

_SAFE = re.compile('[^A-Za-z0-9._-]+')


def _safe_name(path: str) -> str:
    base = Path(path).name or 'file'
    base = _SAFE.sub('_', base)
    sha = hashlib.sha256(path.encode('utf-8')).hexdigest()[:8]
    return f'{base}_{sha}.diff'


def _entries(out_dir: Path, files: list[FileDiff]) -> list[dict]:
    entries: list[dict] = []
    for fd in files:
        diff_path = out_dir / _safe_name(fd.path)
        diff_path.write_text(fd.patch, encoding='utf-8')
        entries.append(
            {
                'path': fd.path,
                'change_kind': fd.change_kind,
                'additions': fd.additions,
                'deletions': fd.deletions,
                'diff_path': str(diff_path),
            }
        )
    return entries


def write_diff_map(*, workspace: GitWorkspace, apply_id: str, worktree: Path, base_commit: str, out_dir: Path) -> Path:
    files = workspace.diff(worktree, base_commit)
    target = out_dir / apply_id
    target.mkdir(parents=True, exist_ok=True)
    index = {'apply_id': apply_id, 'base_commit': base_commit, 'files': _entries(target, files)}
    index_path = target / 'index.json'
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    return index_path
