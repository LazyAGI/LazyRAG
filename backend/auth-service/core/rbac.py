"""
RBAC权限code装饰器
  1. permission_required 声明接口所需权限，用于生成 api_permissions.json，供网关(Kong)在/api/auth/authorize 做鉴权；
  2. 同时在服务端做运行时校验，避免绕过网关直连服务端端口时未鉴权的问题。
"""

from typing import Any, Callable
import functools

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
            for v in list(kwargs.values()) + list(args):
                if hasattr(v, 'role') and getattr(v, 'role', None) is not None:
                    user = v
                    break
            if user is None:
                # 未注入 current_user 时，不允许“悄悄放行”
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
