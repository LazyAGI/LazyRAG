import uuid

from fastapi import APIRouter, Depends, Query

from core.deps import current_user
from core.errors import ErrorCodes, raise_error
from core.rbac import permission_required
from models import User
from schemas.group import (
    GroupAddUsersBody,
    GroupCreateBody,
    GroupCreateResponse,
    GroupDetailResponse,
    GroupListResponse,
    GroupMemberRoleBatchBody,
    GroupRemoveUsersBody,
    GroupUpdateBody,
    GroupUserListResponse,
    OkResponse,
)
from services import group_service


router = APIRouter(prefix='/group', tags=['group'])


def _parse_group_id(group_id: str) -> uuid.UUID:
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
@permission_required('user.read')
def list_groups(
    user: User = Depends(current_user),  # noqa: B008
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(20, ge=1, le=200),  # noqa: B008
    search: str | None = None,
    tenant_id: str | None = None,
):
    items, total = group_service.list_groups(
        page=page,
        page_size=page_size,
        search=search,
        tenant_id=tenant_id,
        current_user_id=user.id,
        is_system_admin=(getattr(user.role, 'name', None) == 'system-admin'),
    )
    return {'groups': items, 'total': total, 'page': page, 'page_size': page_size}


@router.post('', response_model=GroupCreateResponse)
@permission_required('user.admin')
def create_group(body: GroupCreateBody, user: User = Depends(current_user)):  # noqa: B008
    group_name = (body.group_name or '').strip()
    if not group_name:
        raise_error(ErrorCodes.GROUP_NAME_REQUIRED)

    tenant_id = body.tenant_id or user.tenant_id or ''
    group_id = group_service.create_group(
        group_name=group_name,
        tenant_id=tenant_id,
        remark=body.remark or '',
        creator_user_id=user.id,
    )
    return {'group_id': group_id}


@router.get('/{group_id}', response_model=GroupDetailResponse)
@permission_required('user.read')
def get_group(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    gid = _parse_group_id(group_id)
    detail = group_service.get_group(gid)
    if not detail:
        raise_error(ErrorCodes.GROUP_NOT_FOUND)
    return detail


@router.patch('/{group_id}', response_model=OkResponse)
@permission_required('user.admin')
def update_group(
    group_id: str,
    body: GroupUpdateBody,
    _: User = Depends(current_user),  # noqa: B008
):
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
    gid = _parse_group_id(group_id)
    group_service.delete_group(gid)
    return {'ok': True}


@router.get('/{group_id}/user', response_model=GroupUserListResponse)
@permission_required('user.admin')
def list_group_users(group_id: str, _: User = Depends(current_user)):  # noqa: B008
    gid = _parse_group_id(group_id)
    users = group_service.list_group_users(gid)
    return {'users': users}


def _parse_user_ids(user_ids: list[str]) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    for value in user_ids:
        try:
            result.append(uuid.UUID(value))
        except (ValueError, TypeError):
            raise_error(ErrorCodes.USER_NOT_FOUND, extra_msg=value)
    return result


@router.post('/{group_id}/user', response_model=OkResponse)
@permission_required('user.admin')
def add_group_users(
    group_id: str,
    body: GroupAddUsersBody,
    operator: User = Depends(current_user),  # noqa: B008
):
    gid = _parse_group_id(group_id)
    role = (body.role or 'member').strip() or 'member'
    uids = _parse_user_ids(body.user_ids or [])
    group_service.add_group_users(gid, uids, role=role, operator_id=operator.id)
    return {'ok': True}


@router.post('/{group_id}/user/remove', response_model=OkResponse)
@permission_required('user.admin')
def remove_group_users(
    group_id: str,
    body: GroupRemoveUsersBody,
    _: User = Depends(current_user),  # noqa: B008
):
    gid = _parse_group_id(group_id)
    uids = _parse_user_ids(body.user_ids or [])
    group_service.remove_group_users(gid, uids)
    return {'ok': True}


@router.patch('/{group_id}/user/role', response_model=OkResponse)
@permission_required('user.admin')
def set_member_roles_batch(
    group_id: str,
    body: GroupMemberRoleBatchBody,
    _: User = Depends(current_user),  # noqa: B008
):
    gid = _parse_group_id(group_id)
    uids = _parse_user_ids(body.user_ids or [])
    group_service.set_member_roles_batch(gid, uids, (body.role or '').strip())
    return {'ok': True}
