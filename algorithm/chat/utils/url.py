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
        """判断是否符合 Windows 路径特征（盘符或 UNC）"""
        return _windows_drive.match(s) is not None or s.startswith('\\\\')
    return (
        _looks_like_windows_path(s) or
        s.startswith(('/', './', '../'))
    )


_QUOTED_SEGMENT = re.compile(r"(?:^|/)(['\"`])[^/]+\1(?:$|/)")


def is_sane_posix_path(s: str) -> bool:
    """
    严格版 POSIX 路径校验：
    1) 仍需是 path-like（/、./、../ 开头等）
    2) 不含 NUL/控制字符
    3) 不含被成对引号包裹的路径段（如 .../'img_url'）
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
