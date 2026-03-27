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
    """批量修改组内成员角色，user_ids 支持单个或多个，与 role 一起使用"""
    user_ids: list[str]  # UUID 字符串数组
    role: str


class GroupPermissionsBody(BaseModel):
    """组权限全量设置：权限组 code 列表，与角色权限并集后生效，不重复存储"""
    permission_groups: list[str]


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


class GroupBasicResponse(BaseModel):
    """用户组基础信息"""
    group_id: str
    group_name: str
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


class GroupPermissionsResponse(BaseModel):
    """组绑定的权限组 code 列表"""
    permission_groups: list[str]


class OkResponse(BaseModel):
    """通用 ok 返回"""
    ok: bool = True
