from pydantic import BaseModel


class RoleCreateBody(BaseModel):
    name: str


class RolePermissionsBody(BaseModel):
    permission_groups: list[str]


class PermissionGroupItem(BaseModel):
    """权限组项"""
    id: str  # UUID string
    code: str
    description: str = ''
    module: str = ''
    action: str = ''


class RoleItem(BaseModel):
    """角色项"""
    id: str  # UUID string
    name: str
    built_in: bool


class RoleCreateResponse(BaseModel):
    """创建角色返回"""
    id: str  # UUID string
    name: str
    built_in: bool


class RolePermissionsResponse(BaseModel):
    """角色权限查询返回"""
    role_id: str  # UUID string
    permission_groups: list[str]


class OkResponse(BaseModel):
    """通用 ok 返回"""
    ok: bool = True
