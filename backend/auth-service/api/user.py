from fastapi import APIRouter, Depends, Query

from core.deps import current_user
from core.rbac import permission_required
from models import User
from schemas.user import OkResponse, ResetPasswordBody, UserListResponse, UserRoleBody
from services import user_service


router = APIRouter(prefix='/api/user', tags=['user'])


@router.get('', response_model=UserListResponse)
@permission_required('user.admin')
def list_users(
    _: User = Depends(current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    tenant_id: str | None = None,
):
    """分页查询用户列表，支持按关键词、租户筛选"""
    items, total = user_service.list_users(page=page, page_size=page_size, search=search, tenant_id=tenant_id)
    return {'users': items, 'total': total, 'page': page, 'page_size': page_size}


@router.patch('/{user_id}', response_model=OkResponse)
@permission_required('user.admin')
def set_user_role(user_id: int, body: UserRoleBody, _: User = Depends(current_user)):
    """修改指定用户的角色"""
    user_service.set_user_role(user_id, body.role_id)
    return {'ok': True}


@router.patch('/{user_id}/reset_password', response_model=OkResponse)
@permission_required('user.admin')
def reset_password(user_id: int, body: ResetPasswordBody, _: User = Depends(current_user)):
    """重置指定用户的密码，新密码需符合强度要求"""
    user_service.reset_password(user_id, body.new_password or '')
    return {'ok': True}
