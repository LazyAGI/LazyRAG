import uuid

from fastapi import APIRouter, Depends, Query

from core.deps import current_user
from core.rbac import permission_required
from models import User
from schemas.user import (
    CreateUserBody,
    CreateUserResponse,
    OkResponse,
    ResetPasswordBody,
    UserDetailResponse,
    UserListResponse,
    UserRoleBatchBody,
    UserRoleBody,
)
from services import user_service


router = APIRouter(prefix='/user', tags=['user'])


@router.post('', response_model=CreateUserResponse)
@permission_required('user.admin')
def create_user(body: CreateUserBody, _: User = Depends(current_user)):  # noqa: B008
    """System-admin creates a user. Default role is user; can assign any role for high-privilege users."""
    role_id = None
    if body.role_id:
        try:
            role_id = uuid.UUID(body.role_id)
        except (ValueError, TypeError):
            from core.errors import ErrorCodes, raise_error
            raise_error(ErrorCodes.ROLE_NOT_FOUND)
    result = user_service.create_user(
        username=body.username,
        password=body.password,
        role_id=role_id,
        email=body.email,
        tenant_id=body.tenant_id or '',
        disabled=body.disabled,
    )
    return result


@router.get('', response_model=UserListResponse)
@permission_required('user.admin')
def list_users(
    _: User = Depends(current_user),  # noqa: B008
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(20, ge=1, le=200),  # noqa: B008
    search: str | None = None,
    tenant_id: str | None = None,
):
    """分页查询用户列表，支持按关键词、租户筛选"""
    items, total = user_service.list_users(page=page, page_size=page_size, search=search, tenant_id=tenant_id)
    return {'users': items, 'total': total, 'page': page, 'page_size': page_size}


def _parse_user_id(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except (ValueError, TypeError):
        from core.errors import ErrorCodes, raise_error
        raise_error(ErrorCodes.USER_NOT_FOUND)


def _parse_user_ids(user_ids: list[str]) -> list[uuid.UUID]:
    result = []
    for s in user_ids:
        try:
            result.append(uuid.UUID(s))
        except (ValueError, TypeError):
            from core.errors import ErrorCodes, raise_error
            raise_error(ErrorCodes.USER_NOT_FOUND, extra_msg=s)
    return result


@router.patch('/roles', response_model=OkResponse)
@permission_required('user.admin')
def set_user_roles_batch(body: UserRoleBatchBody, _: User = Depends(current_user)):  # noqa: B008
    """Update system roles in batch for the specified users."""
    uids = _parse_user_ids(body.user_ids or [])
    try:
        rid = uuid.UUID(body.role_id)
    except (ValueError, TypeError):
        from core.errors import ErrorCodes, raise_error
        raise_error(ErrorCodes.ROLE_NOT_FOUND)
    user_service.set_user_roles_batch(uids, rid)
    return {'ok': True}


@router.get('/{user_id}', response_model=UserDetailResponse)
@permission_required('user.admin')
def get_user(user_id: str, _: User = Depends(current_user)):  # noqa: B008
    """查询用户详情（需 user.admin）。"""
    uid = _parse_user_id(user_id)
    return user_service.get_user(uid)


@router.patch('/{user_id}', response_model=OkResponse)
@permission_required('user.admin')
def set_user_role(user_id: str, body: UserRoleBody, _: User = Depends(current_user)):  # noqa: B008
    """修改指定用户的角色"""
    uid = _parse_user_id(user_id)
    try:
        rid = uuid.UUID(body.role_id)
    except (ValueError, TypeError):
        from core.errors import ErrorCodes, raise_error
        raise_error(ErrorCodes.ROLE_NOT_FOUND)
    user_service.set_user_role(uid, rid)
    return {'ok': True}


@router.patch('/{user_id}/reset_password', response_model=OkResponse)
@permission_required('user.admin')
def reset_password(user_id: str, body: ResetPasswordBody, _: User = Depends(current_user)):  # noqa: B008
    """重置指定用户的密码，新密码需符合强度要求"""
    user_service.reset_password(_parse_user_id(user_id), body.new_password or '')
    return {'ok': True}
