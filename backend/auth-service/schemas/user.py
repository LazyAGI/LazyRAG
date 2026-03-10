from pydantic import BaseModel


class UserRoleBody(BaseModel):
    role_id: int


class ResetPasswordBody(BaseModel):
    new_password: str


class UserItem(BaseModel):
    """用户列表项"""
    user_id: str
    username: str
    display_name: str = ''
    email: str | None = None
    phone: str | None = None
    status: str  # 'active' | 'inactive'（由 disabled 派生）
    tenant_id: str | None = None
    role_id: int
    role_name: str


class UserListResponse(BaseModel):
    """用户列表"""
    users: list[UserItem]
    total: int
    page: int
    page_size: int


class OkResponse(BaseModel):
    """通用 ok 返回"""
    ok: bool = True
