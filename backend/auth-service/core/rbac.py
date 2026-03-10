"""
RBAC权限code装饰器
  1. permission_required 声明接口所需权限，用于生成 api_permissions.json，供网关(Kong)在/api/auth/authorize 做鉴权；
  2. 接口层仅使用 current_user 获取当前用户，不再做权限/管理员二次校验。
"""

from typing import Any, Callable


def permission_required(*permissions: str):
    perm_set = set(permissions)

    def decorator(fn: Callable[..., Any]):
        fn.__required_permissions__ = perm_set
        return fn

    return decorator

