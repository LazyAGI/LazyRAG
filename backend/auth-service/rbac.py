"""Permission decorator for static analysis only. Actual RBAC is done at Kong + auth-service."""
from __future__ import annotations

from typing import Any, Callable


def permission_required(*permissions: str):
    """Mark route as requiring at least one of the given permission groups. Used by extract_api_permissions.py."""
    perm_set = set(permissions)

    def decorator(fn: Callable[..., Any]):
        setattr(fn, "__required_permissions__", perm_set)
        return fn

    return decorator
