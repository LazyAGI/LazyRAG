from pydantic import BaseModel


class CreateUserBody(BaseModel):
    username: str
    password: str
    role_id: str | None = None  # Default: user role
    email: str | None = None
    tenant_id: str = ''
    disabled: bool = False


class CreateUserResponse(BaseModel):
    user_id: str
    username: str
    role_id: str
    role_name: str


class UserRoleBody(BaseModel):
    role_id: str  # UUID string


class UserRoleBatchBody(BaseModel):
    """直接给用户设置系统角色（与 group 无关），user_ids 支持单个或多个"""
    user_ids: list[str]  # 用户 UUID 字符串数组
    role_id: str  # 角色 UUID 字符串


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
    role_id: str  # UUID string
    role_name: str


class UserListResponse(BaseModel):
    """用户列表"""
    users: list[UserItem]
    total: int
    page: int
    page_size: int


class UserDetailResponse(BaseModel):
    """用户详情"""
    user_id: str
    username: str
    display_name: str = ''
    email: str | None = None
    phone: str | None = None
    status: str  # 'active' | 'inactive'
    tenant_id: str | None = None
    role_id: str
    role_name: str


class OkResponse(BaseModel):
    """通用 ok 返回"""
    ok: bool = True
