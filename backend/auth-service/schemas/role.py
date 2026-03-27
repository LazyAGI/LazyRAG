from pydantic import BaseModel


class RoleCreateBody(BaseModel):
    name: str


class RolePermissionsBody(BaseModel):
    permission_groups: list[str]


class PermissionGroupItem(BaseModel):
    """Permission group item"""
    id: str  # UUID string
    code: str
    description: str = ''
    module: str = ''
    action: str = ''


class RoleItem(BaseModel):
    """Role item"""
    id: str  # UUID string
    name: str
    built_in: bool


class RoleCreateResponse(BaseModel):
    """Create role response"""
    id: str  # UUID string
    name: str
    built_in: bool


class RolePermissionsResponse(BaseModel):
    """Role permission query response"""
    role_id: str  # UUID string
    permission_groups: list[str]


class OkResponse(BaseModel):
    """Generic ok response"""
    ok: bool = True
