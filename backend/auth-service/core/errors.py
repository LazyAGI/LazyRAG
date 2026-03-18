from dataclasses import dataclass
from typing import Any, Optional, Tuple, Type


ErrorTuple = Tuple[int, int, str]


class ErrorCodes:
    INVALID_USERNAME: ErrorTuple = (400, 1000101, '用户名格式错误')
    USER_ALREADY_EXISTS: ErrorTuple = (400, 1000102, '用户已存在')
    INVALID_PASSWORD: ErrorTuple = (400, 1000103, '密码格式错误')
    LOGIN_LOCKED: ErrorTuple = (400, 1000104, '登录已锁定，请稍后再试')
    INVALID_CREDENTIALS: ErrorTuple = (400, 1000105, '用户名或密码错误')
    USER_DISABLED: ErrorTuple = (400, 1000106, '用户已禁用')

    USERNAME_REQUIRED: ErrorTuple = (400, 1000201, '请填写用户名')
    PASSWORD_REQUIRED: ErrorTuple = (400, 1000202, '请填写密码')
    REFRESH_TOKEN_REQUIRED: ErrorTuple = (401, 1000203, '请提供 refresh_token')
    PASSWORD_CONFIRM_MISMATCH: ErrorTuple = (400, 1000204, '两次输入的密码不一致')
    OLD_PASSWORD_INVALID: ErrorTuple = (400, 1000205, '旧密码错误')
    NEW_PASSWORD_REQUIRED: ErrorTuple = (400, 1000206, '请填写新密码')
    REFRESH_TOKEN_INVALID: ErrorTuple = (401, 1000207, 'refresh_token 无效或已过期')

    UNAUTHORIZED: ErrorTuple = (401, 1000301, '未授权')
    FORBIDDEN: ErrorTuple = (403, 1000302, '无权限')
    ADMIN_REQUIRED: ErrorTuple = (403, 1000303, '需要管理员权限')

    USER_NOT_FOUND: ErrorTuple = (404, 1000401, '用户不存在')
    GROUP_NOT_FOUND: ErrorTuple = (404, 1000402, '用户组不存在')
    ROLE_NOT_FOUND: ErrorTuple = (404, 1000403, '角色不存在')
    GROUP_NAME_REQUIRED: ErrorTuple = (400, 1000404, '请填写用户组名称')
    GROUP_NAME_EMPTY: ErrorTuple = (400, 1000405, '用户组名称不能为空')
    ROLE_REQUIRED: ErrorTuple = (400, 1000406, '请指定角色')
    MEMBERSHIP_NOT_FOUND: ErrorTuple = (404, 1000407, '成员关系不存在')
    ROLE_NAME_REQUIRED: ErrorTuple = (400, 1000408, '请填写角色名称')
    ROLE_NAME_EXISTS: ErrorTuple = (400, 1000409, '角色名称已存在')
    CANNOT_DELETE_BUILTIN_ROLE: ErrorTuple = (400, 1000410, '不能删除内置角色')
    CANNOT_CHANGE_ADMIN_PERMS: ErrorTuple = (400, 1000411, '不能修改系统管理员角色权限')

    DEFAULT_ROLE_NOT_FOUND: ErrorTuple = (500, 1000501, "默认角色 'user' 不存在")

    REDIS_AUTH_FAILED: ErrorTuple = (500, 1000601, 'Redis 认证失败')
    REDIS_UNAVAILABLE: ErrorTuple = (500, 1000602, 'Redis 不可用')


@dataclass
class AppException(Exception):
    http_code: int
    code: int
    message: str
    extra: str | None = None

    def __str__(self) -> str:
        return self.message


class AuthError(AppException):
    pass


def raise_error(
    err: ErrorTuple,
    extra_msg: str | None = None,
    *,
    exc_cls: Type[AppException] = AppException,
) -> None:
    http_code, code, message = err
    raise exc_cls(http_code=http_code, code=code, message=message, extra=extra_msg)


def error_payload_from_exception(exc: AppException) -> dict[str, Any]:
    data: Optional[dict[str, Any]] = {
        'code': exc.code,
        'message': exc.message,
        'ex_mesage': exc.extra or '',
    }
    return {'code': exc.http_code, 'message': exc.message, 'data': data}
