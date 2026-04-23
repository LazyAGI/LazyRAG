"""LocalFS: an fsspec-compatible filesystem over local disk.

Intended for local debugging of skill / memory persistence flows when
the production remote filesystem is not available. ``base_dir`` acts as
a chroot root: all paths are resolved relative to it, and paths that
escape it raise :class:`PermissionError`.
"""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from lazyllm.tools.fs import LazyLLMFSBase


class LocalFS(LazyLLMFSBase):
    """fsspec filesystem backed by local files.

    Supports both read and write operations so skill / memory tooling
    can persist artefacts during local debugging. ``base_dir`` acts as
    a chroot root: all paths are resolved relative to it, and paths
    that escape it are rejected.
    """

    protocol = 'localfs'

    def __init__(self, token: str = 'local', base_dir: str = '/', **kwargs):
        super().__init__(token=token, **kwargs)
        self.base_dir = Path(base_dir).expanduser().resolve()

    def _full_path(self, path: str) -> Path:
        path = path or ''
        raw = Path(path)
        if raw.is_absolute():
            resolved = raw.expanduser().resolve()
        else:
            # Use resolve(strict=False) so that we can safely resolve
            # paths that do not yet exist (e.g. before ``_open('w')``).
            resolved = (self.base_dir / raw).expanduser().resolve()
        if resolved != self.base_dir and self.base_dir not in resolved.parents:
            raise PermissionError(f'Path {path!r} escapes base_dir {str(self.base_dir)!r}')
        return resolved

    @staticmethod
    def _entry(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(str(path))
        file_type = 'directory' if path.is_dir() else 'file'
        size = 0 if file_type == 'directory' else path.stat().st_size
        return {'name': path.as_posix(), 'size': size, 'type': file_type}

    def ls(self, path: str, detail: bool = True, **kwargs) -> List[Any]:
        target = self._full_path(path)
        if not target.exists():
            raise FileNotFoundError(str(target))

        if target.is_file():
            entries = [self._entry(target)]
        else:
            children = sorted(target.iterdir(), key=lambda p: p.name)
            entries = [self._entry(child) for child in children]

        if detail:
            return entries
        return [entry['name'] for entry in entries]

    def info(self, path: str, **kwargs) -> Dict[str, Any]:
        return self._entry(self._full_path(path))

    def exists(self, path: str, **kwargs) -> bool:
        try:
            return self._full_path(path).exists()
        except PermissionError:
            return False

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        target = self._full_path(path)
        target.mkdir(parents=True, exist_ok=exist_ok)

    def mkdir(self, path: str, create_parents: bool = True, **kwargs) -> None:
        self.makedirs(path, exist_ok=create_parents)

    def rm(self, path: str, recursive: bool = False, maxdepth: Optional[int] = None) -> None:
        target = self._full_path(path)
        if not target.exists():
            raise FileNotFoundError(str(target))
        if target == self.base_dir:
            raise PermissionError('Refusing to remove base_dir itself')
        if target.is_dir():
            if not recursive:
                raise IsADirectoryError(
                    f'{target} is a directory; pass recursive=True to remove it'
                )
            shutil.rmtree(target)
        else:
            target.unlink()

    def _open(
        self,
        path: str,
        mode: str = 'rb',
        block_size: Optional[int] = None,
        **kwargs,
    ):
        target = self._full_path(path)
        is_write = any(flag in mode for flag in ('w', 'a', 'x', '+'))
        if is_write:
            if target.exists() and target.is_dir():
                raise IsADirectoryError(str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            if target.is_dir():
                raise IsADirectoryError(str(target))
        # fsspec may pass internal open kwargs that Python's built-in open()
        # does not accept.
        kwargs.pop('autocommit', None)
        kwargs.pop('cache_options', None)
        kwargs.pop('compression', None)
        return open(target, mode=mode, **kwargs)


# Backward-compatible alias for existing call sites.
LocalFileSystem = LocalFS
