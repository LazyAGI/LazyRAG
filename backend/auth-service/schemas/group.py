from pydantic import BaseModel


class GroupCreateBody(BaseModel):
    group_name: str
    remark: str | None = None
    tenant_id: str | None = None


class GroupUpdateBody(BaseModel):
    group_name: str | None = None
    remark: str | None = None
    tenant_id: str | None = None


class GroupAddUsersBody(BaseModel):
    user_ids: list[int]
    role: str | None = None


class GroupRemoveUsersBody(BaseModel):
    user_ids: list[int]


class GroupMemberRoleBody(BaseModel):
    role: str


# ----- 响应 -----
class GroupItem(BaseModel):
    """用户组列表项"""
    group_id: str
    group_name: str
    remark: str | None = None
    tenant_id: str | None = None


class GroupListResponse(BaseModel):
    """用户组列表"""
    groups: list[GroupItem]
    total: int
    page: int
    page_size: int


class GroupDetailResponse(BaseModel):
    """用户组详情"""
    group_id: str
    group_name: str
    remark: str | None = None
    tenant_id: str | None = None


class GroupCreateResponse(BaseModel):
    """创建用户组返回"""
    group_id: str


class GroupUserItem(BaseModel):
    """组内用户项"""
    user_id: str
    username: str
    role: str
    tenant_id: str | None = None


class GroupUserListResponse(BaseModel):
    """组内用户列表"""
    users: list[GroupUserItem]


class OkResponse(BaseModel):
    """通用 ok 返回"""
    ok: bool = True
