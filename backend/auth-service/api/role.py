import uuid

from fastapi import APIRouter, Depends

from core.deps import current_user
from core.rbac import permission_required
from models import User
from schemas.role import (
    OkResponse,
    PermissionGroupItem,
    RoleCreateBody,
    RoleCreateResponse,
    RoleItem,
    RolePermissionsBody,
    RolePermissionsResponse,
)
from services import role_service


router = APIRouter(prefix='/role', tags=['role'])


@router.get('/permission-groups', response_model=list[PermissionGroupItem])
@permission_required('user.admin')
def list_permission_groups(_: User = Depends(current_user)):  # noqa: B008
    """查询所有权限组列表(id、name)，用于角色配置权限时选择"""
    return role_service.list_permission_groups()


@router.get('', response_model=list[RoleItem])
@permission_required('user.admin')
def list_roles(_: User = Depends(current_user)):  # noqa: B008
    """查询所有角色列表(id、name、built_in)"""
    return role_service.list_roles()


@router.post('', response_model=RoleCreateResponse)
@permission_required('user.admin')
def create_role(body: RoleCreateBody, _: User = Depends(current_user)):  # noqa: B008
    """创建新角色，名称不可与已有角色重复"""
    return role_service.create_role(body.name.strip())


def _parse_role_id(role_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(role_id)
    except (ValueError, TypeError):
        from core.errors import ErrorCodes, raise_error
        raise_error(ErrorCodes.ROLE_NOT_FOUND)


@router.delete('/{role_id}', response_model=OkResponse)
@permission_required('user.admin')
def delete_role(role_id: str, _: User = Depends(current_user)):  # noqa: B008
    """删除指定角色，内置角色不可删除"""
    role_service.delete_role(_parse_role_id(role_id))
    return {'ok': True}


@router.get('/{role_id}/permissions', response_model=RolePermissionsResponse)
@permission_required('user.admin')
def get_role_permissions(role_id: str, _: User = Depends(current_user)):  # noqa: B008
    """查询指定角色已绑定的权限组名称列表"""
    rid = _parse_role_id(role_id)
    permission_groups = role_service.get_role_permissions(rid)
    return {'role_id': str(rid), 'permission_groups': permission_groups}


@router.put('/{role_id}/permissions', response_model=OkResponse)
@permission_required('user.admin')
def set_role_permissions(role_id: str, body: RolePermissionsBody, _: User = Depends(current_user)):  # noqa: B008
    """设置指定角色的权限组(全量覆盖)，管理员角色不可修改"""
    role_service.set_role_permissions(_parse_role_id(role_id), body.permission_groups)
    return {'ok': True}
