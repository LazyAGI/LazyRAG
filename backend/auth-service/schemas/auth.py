from pydantic import BaseModel


# ----- 健康检查 -----
class HealthResponse(BaseModel):
    """健康检查返回"""
    status: str = 'ok'
    timestamp: float


# ----- 注册 -----
class RegisterBody(BaseModel):
    username: str
    password: str
    confirm_password: str
    email: str | None = None
    tenant_id: str | None = None


class RegisterResponse(BaseModel):
    """注册成功返回"""
    success: bool = True
    user_id: str
    tenant_id: str | None = None
    role: str


# ----- 登录 -----
class LoginBody(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录成功返回"""
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    role: str
    expires_in: int
    tenant_id: str | None = None


# ----- 刷新 Token(响应与登录一致) -----
class RefreshBody(BaseModel):
    refresh_token: str


# ----- 校验 Token -----
class ValidateResponse(BaseModel):
    """校验 Token 返回"""
    sub: str
    role: str
    tenant_id: str | None = None
    permissions: list[str]


# ----- 当前用户 -----
class MeResponse(BaseModel):
    """当前用户信息"""
    user_id: str
    username: str
    display_name: str = ''
    email: str | None = None
    status: str  # 'active' | 'inactive'
    role: str
    permissions: list[str]
    tenant_id: str | None = None


# ----- 修改密码 / 登出 -----
class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


class LogoutBody(BaseModel):
    refresh_token: str | None = None


class SuccessResponse(BaseModel):
    """通用成功返回(如修改密码、登出)"""
    success: bool = True


# ----- 鉴权(authorize 用) -----
class AuthorizeBody(BaseModel):
    method: str
    path: str


class AuthorizeResponse(BaseModel):
    """鉴权结果"""
    allowed: bool
