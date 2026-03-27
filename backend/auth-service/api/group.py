import uuid

from fastapi import APIRouter, Depends, Query

from core.deps import current_user
from core.errors import ErrorCodes, raise_error
from core.rbac import permission_required
from models import User
from schemas.group import (
    GroupAddUsersBody,
    GroupBasicResponse,
    GroupCreateBody,
    GroupCreateResponse,
    GroupDetailResponse,
    GroupListResponse,
    GroupMemberRoleBatchBody,
    GroupPermissionsBody,
    GroupPermissionsResponse,
    GroupRemoveUsersBody,
    GroupUpdateBody,
    GroupUserListResponse,
    OkResponse,
)
from services import group_service


router = APIRouter(prefix='/group', tags=['group'])


def _parse_group_id(group_id: str) -> uuid.UUID:
    """将路径参数 group_id 解析为 UUID，非法格式视为组不存在。"""
    try:
        return uuid.UUID(group_id)
    except (ValueError, TypeError):
        raise_error(ErrorCodes.GROUP_NOT_FOUND)


def _parse_user_id(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise_error(ErrorCodes.USER_NOT_FOUND)


@router.get('', response_model=GroupListResponse)
@permission_required('user.admin')
def list_groups(
    _: User = Depends(current_user),  # noqa: B008
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(20, ge=1, le=200),  # noqa: B008
    search: str | None = None,
    tenant_id: str | None = None,
):
    """分页查询用户组列表，支持按关键词、租户筛选"""
    items, total = group_service.list_groups(page=page, page_size=page_size, search=search, tenant_id=tenant_id)
    return {'groups': items, 'total': total, 'page': page, 'page_size': page_size}


@router.post('', response_model=GroupCreateResponse)
@permission_required('user.admin')
def create_group(body: GroupCreateBody, user: User = Depends(current_user)):  # noqa: B008
    """创建用户组，需填写组名、备注、租户等"""
    group_name = (body.group_name or '').strip()
    if not group_name:
        raise_error(ErrorCodes.GROUP_NAME_REQUIRED)
    tenant_id = body.tenant_id or user.tenant_id or ''
    group_id = group_service.create_group(
        group_name=group_name,
        tenant_id=tenant_id,
        remark=(body.remark or ''),
        creator_user_id=user.id,
    )
    return {'group_id': group_id}


@router.get('/{group_id}/basic', response_model=GroupBasicResponse)
def get_group_basic(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    """查询用户组基础信息（已登录即可，用于服务间回填组名）。"""
    gid = _parse_group_id(group_id)
    detail = group_service.get_group(gid)
    if not detail:
        raise_error(ErrorCodes.GROUP_NOT_FOUND)
    return {
        'group_id': detail['group_id'],
        'group_name': detail['group_name'],
        'tenant_id': detail.get('tenant_id'),
    }


@router.get('/{group_id}', response_model=GroupDetailResponse)
@permission_required('user.admin')
def get_group(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    """查询指定用户组详情(组名、备注、租户等)"""
    gid = _parse_group_id(group_id)
    detail = group_service.get_group(gid)
    if not detail:
        raise_error(ErrorCodes.GROUP_NOT_FOUND)
    return detail


@router.patch('/{group_id}', response_model=OkResponse)
@permission_required('user.admin')
def update_group(group_id: str, body: GroupUpdateBody, _: User = Depends(current_user)):  # noqa: B008
    """更新指定用户组(组名、备注、租户)；需 user.admin(由网关鉴权)。"""
    gid = _parse_group_id(group_id)
    group_service.update_group(
        gid,
        group_name=body.group_name.strip() if body.group_name is not None else None,
        remark=body.remark,
        tenant_id=body.tenant_id,
    )
    return {'ok': True}


@router.delete('/{group_id}', response_model=OkResponse)
@permission_required('user.admin')
def delete_group(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    """删除指定用户组"""
    gid = _parse_group_id(group_id)
    group_service.delete_group(gid)
    return {'ok': True}


@router.get('/{group_id}/permissions', response_model=GroupPermissionsResponse)
@permission_required('user.admin')
def get_group_permissions(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    """查询组绑定的权限组；组内成员鉴权时自动拥有这些权限（与角色权限并集）。"""
    gid = _parse_group_id(group_id)
    codes = group_service.get_group_permissions(gid)
    return {'permission_groups': codes}


@router.put('/{group_id}/permissions', response_model=OkResponse)
@permission_required('user.admin')
def set_group_permissions(group_id: str, body: GroupPermissionsBody, _: User = Depends(current_user)):  # noqa: B008
    """全量设置组的权限组；组内成员自动拥有新权限，无需单独写用户表。"""
    gid = _parse_group_id(group_id)
    group_service.set_group_permissions(gid, body.permission_groups or [])
    return {'ok': True}


@router.get('/{group_id}/user', response_model=GroupUserListResponse)
@permission_required('user.admin')
def list_group_users(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    """查询指定用户组内的成员列表(用户 id、用户名、组内角色、租户)"""
    gid = _parse_group_id(group_id)
    users = group_service.list_group_users(gid)
    return {'users': users}


def _parse_user_ids(user_ids: list[str]) -> list[uuid.UUID]:
    result = []
    for s in user_ids:
        try:
            result.append(uuid.UUID(s))
        except (ValueError, TypeError):
            raise_error(ErrorCodes.USER_NOT_FOUND, extra_msg=s)
    return result


@router.post('/{group_id}/user', response_model=OkResponse)
@permission_required('user.admin')
def add_group_users(group_id: str, body: GroupAddUsersBody, operator: User = Depends(current_user)):  # noqa: B008
    """将指定用户批量加入用户组，可指定组内角色(默认 member)，已存在则跳过"""
    gid = _parse_group_id(group_id)
    role = (body.role or 'member').strip() or 'member'
    uids = _parse_user_ids(body.user_ids or [])
    group_service.add_group_users(gid, uids, role=role, operator_id=operator.id)
    return {'ok': True}


@router.post('/{group_id}/user/remove', response_model=OkResponse)
@permission_required('user.admin')
def remove_group_users(group_id: str, body: GroupRemoveUsersBody, _: User = Depends(current_user)):  # noqa: B008
    """从用户组中批量移除指定用户"""
    gid = _parse_group_id(group_id)
    uids = _parse_user_ids(body.user_ids or [])
    group_service.remove_group_users(gid, uids)
    return {'ok': True}


@router.patch('/{group_id}/user/role', response_model=OkResponse)
@permission_required('user.admin')
def set_member_roles_batch(
    group_id: str, body: GroupMemberRoleBatchBody, _: User = Depends(current_user)  # noqa: B008
):
    """修改组内成员角色（支持批量）。user_ids 传一个或多个用户 UUID，与 role 一起使用。"""
    gid = _parse_group_id(group_id)
    uids = _parse_user_ids(body.user_ids or [])
    group_service.set_member_roles_batch(gid, uids, (body.role or '').strip())
    return {'ok': True}
