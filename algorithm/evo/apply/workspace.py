from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from evo.apply.errors import ApplyError


SNAPSHOT_IGNORE = (
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '*.pyc', '*.pyo', '.DS_Store',
)


@dataclass
class DiffResult:
    files_changed: list[str]
    unified_diff_path: Path
    byte_count: int


def snapshot_chat(repo_root: Path, baseline_dir: Path, chat_relpath: str) -> Path:
    src = (repo_root / chat_relpath).resolve()
    if not src.is_dir():
        raise ApplyError('CHAT_DIR_NOT_FOUND', 'chat directory not found',
                         {'path': str(src)})
    dst = (baseline_dir / chat_relpath).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SNAPSHOT_IGNORE))
    return dst


def compute_diff(repo_root: Path, baseline_dir: Path, chat_relpath: str,
                 out_dir: Path) -> DiffResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_target = (baseline_dir / chat_relpath).resolve()
    current_src = (repo_root / chat_relpath).resolve()

    with tempfile.TemporaryDirectory(prefix='evo_apply_diff_') as tmp:
        current_target = Path(tmp) / chat_relpath
        current_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(current_src, current_target,
                        ignore=shutil.ignore_patterns(*SNAPSHOT_IGNORE))

        files = _git_diff_names(baseline_target, current_target)
        rel_files = sorted({_strip_diff_prefix(f, baseline_target, current_target)
                            for f in files if f})
        rel_files = [f for f in rel_files if f]

        unified_text = _git_diff_unified(baseline_target, current_target)

    files_changed_path = out_dir / 'files_changed.json'
    files_changed_path.write_text(
        json.dumps(rel_files, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    unified_path = out_dir / 'unified.diff'
    unified_path.write_text(unified_text, encoding='utf-8')

    return DiffResult(
        files_changed=rel_files,
        unified_diff_path=unified_path,
        byte_count=len(unified_text.encode('utf-8')),
    )


def _git_diff_names(a: Path, b: Path) -> list[str]:
    proc = _run_git_diff(['--name-only', '--no-index', '-z', str(a), str(b)])
    if proc.returncode not in (0, 1):
        raise ApplyError('GIT_DIFF_FAILED', 'git diff --name-only failed',
                         {'returncode': proc.returncode, 'stderr': proc.stderr})
    return [p for p in proc.stdout.split('\0') if p]


def _git_diff_unified(a: Path, b: Path) -> str:
    proc = _run_git_diff(['--no-index', '--unified=3', str(a), str(b)])
    if proc.returncode not in (0, 1):
        raise ApplyError('GIT_DIFF_FAILED', 'git diff --unified failed',
                         {'returncode': proc.returncode, 'stderr': proc.stderr})
    return proc.stdout


def _run_git_diff(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ['git', 'diff', *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise ApplyError('GIT_DIFF_FAILED', 'git binary not found',
                         {'args': args}) from exc


def _strip_diff_prefix(raw_path: str, baseline: Path, current: Path) -> str:
    for root in (baseline, current):
        prefix = str(root) + '/'
        if raw_path.startswith(prefix):
            return raw_path[len(prefix):]
    return raw_path
