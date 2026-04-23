from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from evo.apply.errors import ApplyError

_IGNORE = ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
           '*.pyc', '*.pyo', '.DS_Store', '.git')

_GIT_USER = ['-c', 'user.email=evo@local', '-c', 'user.name=evo']


@dataclass
class FileDiff:
    path: str
    change_kind: str
    additions: int
    deletions: int
    patch: str


def _git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(['git', *args], cwd=str(cwd),
                           capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ApplyError('GIT_DIFF_FAILED', 'git not found',
                         {'args': args}) from exc
    if r.returncode not in (0,):
        raise ApplyError('GIT_DIFF_FAILED',
                         f'git {" ".join(args)} failed',
                         {'returncode': r.returncode, 'stderr': r.stderr})
    return r.stdout


def _kind(code: str) -> str:
    c = code[0] if code else 'M'
    return {'A': 'added', 'M': 'modified', 'D': 'deleted',
            'R': 'renamed', 'C': 'copied'}.get(c, 'modified')


class GitWorkspace:
    def __init__(self, git_dir: Path, chat_source: Path) -> None:
        self._root = git_dir
        self._bare = git_dir / 'chat.git'
        self._worktrees = git_dir / 'worktrees'
        self._chat_source = chat_source

    @property
    def bare(self) -> Path:
        return self._bare

    def worktree_path(self, apply_id: str) -> Path:
        return self._worktrees / f'apply_{apply_id}'

    @staticmethod
    def branch_name(apply_id: str) -> str:
        return f'evo/apply/{apply_id}'

    def ensure_bare(self) -> None:
        if (self._bare / 'HEAD').exists():
            return
        self._bare.mkdir(parents=True, exist_ok=True)
        _git(['init', '--bare', '--initial-branch=main', str(self._bare)],
             self._bare.parent)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_repo = Path(tmp) / 'init'
            _git(['clone', str(self._bare), str(tmp_repo)], Path(tmp))
            _ignore = shutil.ignore_patterns(*_IGNORE)
            for item in self._chat_source.iterdir():
                if item.name in _IGNORE:
                    continue
                dest = tmp_repo / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, ignore=_ignore)
                else:
                    shutil.copy2(item, dest)
            _git(['add', '-A'], tmp_repo)
            _git(_GIT_USER + ['commit', '-m', 'initial chat snapshot'], tmp_repo)
            _git(['push', 'origin', 'main'], tmp_repo)

    def create_worktree(self, apply_id: str,
                        base_ref: str = 'main') -> tuple[Path, str]:
        self._worktrees.mkdir(parents=True, exist_ok=True)
        wt = self.worktree_path(apply_id)
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
        _git(['worktree', 'add', '-b', self.branch_name(apply_id),
              str(wt), base_ref], self._bare)
        sha = self.head_commit(wt)
        return wt, sha

    def commit_all(self, worktree: Path, msg: str) -> str | None:
        _git(['add', '-A'], worktree)
        status = _git(['status', '--porcelain'], worktree).strip()
        if not status:
            return None
        _git(_GIT_USER + ['commit', '-m', msg], worktree)
        return self.head_commit(worktree)

    def head_commit(self, worktree: Path) -> str:
        return _git(['rev-parse', 'HEAD'], worktree).strip()

    def remove_worktree(self, apply_id: str) -> None:
        wt = self.worktree_path(apply_id)
        if wt.exists():
            try:
                _git(['worktree', 'remove', '--force', str(wt)], self._bare)
            except ApplyError:
                shutil.rmtree(wt, ignore_errors=True)
        try:
            _git(['branch', '-D', self.branch_name(apply_id)], self._bare)
        except ApplyError:
            pass
        _git(['worktree', 'prune'], self._bare)

    def diff(self, worktree: Path, base_commit: str) -> list[FileDiff]:
        raw = _git(['diff', '--name-status', f'{base_commit}..HEAD'], worktree).strip()
        if not raw:
            return []
        out: list[FileDiff] = []
        for line in raw.splitlines():
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            kind = _kind(parts[0])
            path = parts[-1]
            patch = _git(['diff', f'{base_commit}..HEAD', '--', path], worktree)
            adds = sum(1 for ln in patch.splitlines()
                       if ln.startswith('+') and not ln.startswith('+++'))
            dels = sum(1 for ln in patch.splitlines()
                       if ln.startswith('-') and not ln.startswith('---'))
            out.append(FileDiff(path=path, change_kind=kind,
                                additions=adds, deletions=dels, patch=patch))
        return out
