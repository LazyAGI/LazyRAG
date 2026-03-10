"""用户组业务逻辑：API 层调用本模块，本模块调用 Repository。"""
import uuid

from core.database import SessionLocal
from core.errors import ErrorCodes, raise_error
from repositories import GroupRepository, UserGroupRepository, UserRepository


def list_groups(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    tenant_id: str | None = None,
) -> tuple[list[dict], int]:
    """分页查询用户组列表。返回 (groups 列表项, total)。"""
    with SessionLocal() as db:
        groups, total = GroupRepository.list_paginated(db, page, page_size, search, tenant_id)
        items = [
            {
                'group_id': str(g.id),
                'group_name': g.group_name,
                'remark': g.remark,
                'tenant_id': g.tenant_id,
            }
            for g in groups
        ]
        return items, int(total)


def create_group(
    group_name: str,
    tenant_id: str,
    remark: str = '',
    creator_user_id: int | None = None,
) -> str:
    """创建用户组。返回 group_id (UUID 字符串)。"""
    with SessionLocal() as db:
        g = GroupRepository.create(
            db,
            tenant_id=tenant_id,
            group_name=group_name,
            remark=remark,
            creator_user_id=creator_user_id,
        )
        return str(g.id)


def get_group(group_id: uuid.UUID) -> dict | None:
    """查询用户组详情，不存在返回 None。"""
    with SessionLocal() as db:
        g = GroupRepository.get_by_id(db, group_id)
        if not g:
            return None
        return {
            'group_id': str(g.id),
            'group_name': g.group_name,
            'remark': g.remark,
            'tenant_id': g.tenant_id,
        }


def update_group(
    group_id: uuid.UUID,
    group_name: str | None = None,
    remark: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """更新用户组。不存在或校验失败抛错。"""
    with SessionLocal() as db:
        g = GroupRepository.get_by_id(db, group_id)
        if not g:
            raise_error(ErrorCodes.GROUP_NOT_FOUND)
        if group_name is not None:
            name = group_name.strip()
            if not name:
                raise_error(ErrorCodes.GROUP_NAME_EMPTY)
            g.group_name = name
        if remark is not None:
            g.remark = remark
        if tenant_id is not None:
            g.tenant_id = tenant_id
        db.commit()


def delete_group(group_id: uuid.UUID) -> None:
    """删除用户组。不存在抛错。"""
    with SessionLocal() as db:
        g = GroupRepository.get_by_id(db, group_id)
        if not g:
            raise_error(ErrorCodes.GROUP_NOT_FOUND)
        GroupRepository.delete(db, g)


def list_group_users(group_id: uuid.UUID) -> list[dict]:
    """查询用户组内成员列表。"""
    with SessionLocal() as db:
        rows = UserGroupRepository.list_by_group_id(db, group_id)
        return [
            {
                'user_id': str(r.user_id),
                'username': r.user.username,
                'role': r.role,
                'tenant_id': r.tenant_id,
            }
            for r in rows
        ]


def add_group_users(
    group_id: uuid.UUID,
    user_ids: list[int],
    role: str = 'member',
    operator_id: int | None = None,
) -> None:
    """批量添加用户到用户组。组不存在或某用户不存在抛错。"""
    with SessionLocal() as db:
        group = GroupRepository.get_by_id(db, group_id)
        if not group:
            raise_error(ErrorCodes.GROUP_NOT_FOUND)
        for uid in user_ids:
            user = UserRepository.get_by_id(db, uid)
            if not user:
                raise_error(ErrorCodes.USER_NOT_FOUND, extra_msg=str(uid))
            exists = UserGroupRepository.get_by_group_and_user(db, group_id, uid, group.tenant_id)
            if exists:
                continue
            UserGroupRepository.add(
                db,
                tenant_id=group.tenant_id,
                user_id=uid,
                group_id=group_id,
                role=role,
                creator_user_id=operator_id,
            )


def remove_group_users(group_id: uuid.UUID, user_ids: list[int]) -> None:
    """从用户组批量移除用户。"""
    with SessionLocal() as db:
        UserGroupRepository.remove_by_group_and_users(db, group_id, user_ids)


def set_member_role(group_id: uuid.UUID, user_id: int, role: str) -> None:
    """修改用户在组内的角色。成员不存在或 role 为空抛错。"""
    if not (role or '').strip():
        raise_error(ErrorCodes.ROLE_REQUIRED)
    with SessionLocal() as db:
        row = UserGroupRepository.get_by_group_and_user(db, group_id, user_id)
        if not row:
            raise_error(ErrorCodes.MEMBERSHIP_NOT_FOUND)
        UserGroupRepository.set_member_role(db, row, role.strip())
