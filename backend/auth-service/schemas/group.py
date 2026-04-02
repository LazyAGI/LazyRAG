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
    user_ids: list[str]  # UUID strings
    role: str | None = None


class GroupRemoveUsersBody(BaseModel):
    user_ids: list[str]  # UUID strings


class GroupMemberRoleBody(BaseModel):
    role: str


class GroupMemberRoleBatchBody(BaseModel):
    """Batch update member roles in a group. user_ids supports one or multiple values and must be used with role."""
    user_ids: list[str]  # Array of UUID strings
    role: str


# ----- Responses -----
class GroupItem(BaseModel):
    """Group list item"""
    group_id: str
    group_name: str
    remark: str | None = None
    tenant_id: str | None = None


class GroupListResponse(BaseModel):
    """Group list"""
    groups: list[GroupItem]
    total: int
    page: int
    page_size: int


class GroupDetailResponse(BaseModel):
    """Group details"""
    group_id: str
    group_name: str
    remark: str | None = None
    tenant_id: str | None = None


class GroupCreateResponse(BaseModel):
    """Create group response"""
    group_id: str


class GroupUserItem(BaseModel):
    """Group user item"""
    username: str
    role: str
    tenant_id: str | None = None


class GroupUserListResponse(BaseModel):
    """Group user list"""
    users: list[GroupUserItem]


class OkResponse(BaseModel):
    """Generic ok response"""
    ok: bool = True
