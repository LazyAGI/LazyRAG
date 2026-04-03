import functools
from typing import Any, Callable

from core.errors import ErrorCodes, raise_error
from core.permissions import get_effective_permission_codes


def permission_required(*permissions: str):
    perm_set = set(permissions)

    def decorator(fn: Callable[..., Any]):
        fn.__required_permissions__ = perm_set
        if not perm_set:
            return fn

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            user = None
            for value in list(kwargs.values()) + list(args):
                if hasattr(value, 'role') and getattr(value, 'role', None) is not None:
                    user = value
                    break

            if user is None:
                raise_error(ErrorCodes.UNAUTHORIZED)

            role = getattr(user, 'role', None)
            role_name = getattr(role, 'name', None)
            if role_name == 'system-admin':
                return fn(*args, **kwargs)

            user_perms = get_effective_permission_codes(user)
            if user_perms & perm_set:
                return fn(*args, **kwargs)
            raise_error(ErrorCodes.FORBIDDEN)

        return wrapper

    return decorator
