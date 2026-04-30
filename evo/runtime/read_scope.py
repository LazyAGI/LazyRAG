from __future__ import annotations
import fnmatch
import importlib.util
from functools import lru_cache
from pathlib import Path
from evo.runtime.code_config import ReadScope
def is_readable(file_path: str | Path, scope: ReadScope) -> tuple[bool, str]:
    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        return (False, f'not a file: {file_path}')
    posix = p.as_posix()
    for pkg in scope.third_party_packages:
        pkg_dir = _package_dir(pkg)
        if pkg_dir and _under(p, pkg_dir):
            return (True, f'package:{pkg}')
    for excl in scope.exclude_globs:
        if fnmatch.fnmatch(posix, excl):
            return (False, f'excluded by glob: {excl}')
    for root in scope.project_roots:
        if _under(p, root):
            return (True, f'project:{root}')
    for root in scope.extra_roots:
        if _under(p, root):
            return (True, f'extra:{root}')
    return (False, 'outside read_scope')
def resolve_in_scope(file_path: str | Path, scope: ReadScope) -> Path:
    raw = Path(file_path).expanduser()
    if not raw.is_absolute():
        for root in (*scope.project_roots, *scope.extra_roots):
            candidate = Path(root) / raw
            (ok, _why) = is_readable(candidate, scope)
            if ok:
                return candidate.resolve()
    (ok, why) = is_readable(file_path, scope)
    if not ok:
        raise PermissionError(f'{file_path}: {why}')
    return Path(file_path).expanduser().resolve()
def iter_scope_files(scope: ReadScope, *, suffixes: tuple[str, ...]=('.py',), limit: int=500) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for root in (*scope.project_roots, *scope.extra_roots):
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue
        for p in root.rglob('*'):
            if not p.is_file() or p.suffix not in suffixes:
                continue
            if any((fnmatch.fnmatch(p.as_posix(), g) for g in scope.exclude_globs)):
                continue
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
            if len(out) >= limit:
                return out
    return out
def iter_package_files(package: str, *, suffixes: tuple[str, ...]=('.py',), limit: int=1000) -> list[Path]:
    pkg_dir = _package_dir(package)
    if pkg_dir is None or not pkg_dir.is_dir():
        return []
    out: list[Path] = []
    for p in pkg_dir.rglob('*'):
        if p.is_file() and p.suffix in suffixes:
            out.append(p)
            if len(out) >= limit:
                break
    return out
@lru_cache(maxsize=64)
def _package_dir(pkg: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(pkg)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    return Path(spec.origin).resolve().parent
def _under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(Path(root).expanduser().resolve())
    except ValueError:
        return False
    return True
