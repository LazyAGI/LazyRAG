from __future__ import annotations

import json
import logging
from pathlib import Path

from evo.apply import GitWorkspace
from evo.apply.errors import ApplyError
from evo.runtime.config import EvoConfig

log = logging.getLogger('evo.apply.merge')


def merge_apply(
    *,
    apply_id: str,
    workspace: GitWorkspace,
    config: EvoConfig,
    strategy: str = 'merge-commit',
) -> dict:
    """Merge an apply worktree back into the baseline branch.

    *strategy* must be one of ``merge-commit``, ``squash``, ``fast-forward``.
    Returns a dict with ``merge_id``, ``base_commit``, ``merge_commit``,
    ``strategy``, ``status``.
    """
    if strategy not in ('merge-commit', 'squash', 'fast-forward'):
        raise ApplyError('MERGE_INVALID_STRATEGY',
                         f'unknown strategy {strategy!r}')
    worktree = workspace.worktree_path(apply_id)
    if not worktree.exists():
        raise ApplyError('MERGE_WORKTREE_MISSING',
                         f'worktree for {apply_id} not found')
    # Resolve final commit in worktree
    import subprocess
    try:
        sha = subprocess.check_output(
            ['git', '-C', str(worktree), 'rev-parse', 'HEAD'],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ApplyError('MERGE_GIT_ERROR', 'cannot resolve HEAD', {'stderr': exc.stderr})
    baseline = 'main'  # TODO: make configurable
    repo_dir = workspace.bare
    try:
        if strategy == 'fast-forward':
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'checkout', baseline],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'merge', '--ff-only', sha],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif strategy == 'squash':
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'checkout', baseline],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'merge', '--squash', sha],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'commit', '-m',
                 f'evo squash merge apply={apply_id}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:  # merge-commit
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'checkout', baseline],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(
                ['git', '-C', str(repo_dir), 'merge', '--no-ff', '-m',
                 f'evo merge apply={apply_id}', sha],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        merge_sha = subprocess.check_output(
            ['git', '-C', str(repo_dir), 'rev-parse', 'HEAD'],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ApplyError('MERGE_CONFLICT',
                         'merge failed (conflict or git error)',
                         {'stderr': getattr(exc, 'stderr', None) or str(exc)})
    return {
        'merge_id': f'merge_{apply_id}',
        'apply_id': apply_id,
        'base_commit': sha,
        'merge_commit': merge_sha,
        'strategy': strategy,
        'status': 'merged',
    }
