import os
import re
from urllib.parse import urlparse


def is_url(s):
    try:
        res = urlparse(s)
        return bool(res.scheme and (res.netloc or res.scheme == 'file'))
    except Exception:
        return False


def is_path_like(s):
    _windows_drive = re.compile(r'^[a-zA-Z]:[\\/]')

    def _looks_like_windows_path(s: str) -> bool:
        """Check whether the string looks like a Windows path (drive letter or UNC)."""
        return _windows_drive.match(s) is not None or s.startswith('\\\\')
    return (
        _looks_like_windows_path(s)
        or s.startswith(('/', './', '../'))
    )


_QUOTED_SEGMENT = re.compile(r"(?:^|/)(['\"`])[^/]+\1(?:$|/)")


def is_sane_posix_path(s: str) -> bool:
    """
    Strict POSIX path validation:
    1) Must still be path-like (starts with /, ./, ../, etc.)
    2) No NUL/control characters
    3) No path segments wrapped in matching quotes (e.g. .../'img_url')
    """
    if not isinstance(s, str) or not s:
        return False
    if not is_path_like(s):
        return False
    if '\x00' in s or any(ord(ch) < 32 for ch in s):
        return False
    if _QUOTED_SEGMENT.search(s):
        return False
    return True


def is_valid_path(s):
    return is_url(s) or is_sane_posix_path(s)


def get_url_basename(s):
    parsed = urlparse(s)
    filename = os.path.basename(parsed.path if is_url(s) else s)
    return filename
