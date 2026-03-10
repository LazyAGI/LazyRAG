"""用户业务逻辑：API 层调用本模块，本模块调用 Repository。"""
from datetime import datetime, timezone

from core.database import SessionLocal
from core.errors import ErrorCodes, raise_error
from repositories import RoleRepository, UserRepository
from services.auth_service import hash_password, validate_password


def list_users(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    tenant_id: str | None = None,
) -> tuple[list[dict], int]:
    """分页查询用户列表。返回 (users 列表项, total)。"""
    with SessionLocal() as db:
        users, total = UserRepository.list_paginated(db, page, page_size, search, tenant_id)
        items = [
            {
                'user_id': str(u.id),
                'username': u.username,
                'display_name': u.display_name or u.username,
                'email': u.email,
                'phone': u.phone or None,
                'status': 'inactive' if u.disabled else 'active',
                'tenant_id': u.tenant_id,
                'role_id': u.role_id,
                'role_name': u.role.name,
            }
            for u in users
        ]
        return items, int(total)


def set_user_role(user_id: int, role_id: int) -> None:
    """修改用户角色。用户或角色不存在抛错。"""
    with SessionLocal() as db:
        user = UserRepository.get_by_id(db, user_id, load_role=True)
        if not user:
            raise_error(ErrorCodes.USER_NOT_FOUND)
        role = RoleRepository.get_by_id(db, role_id)
        if not role:
            raise_error(ErrorCodes.ROLE_NOT_FOUND)
        user.role_id = role.id
        db.commit()


def reset_password(user_id: int, new_password: str) -> None:
    """重置用户密码。用户不存在或密码不符合强度抛错。"""
    new_password = (new_password or '').strip()
    if not new_password:
        raise_error(ErrorCodes.NEW_PASSWORD_REQUIRED)
    if not validate_password(new_password):
        raise_error(ErrorCodes.INVALID_PASSWORD)
    with SessionLocal() as db:
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise_error(ErrorCodes.USER_NOT_FOUND)
        user.password_hash = hash_password(new_password)
        user.updated_pwd_time = datetime.now(timezone.utc)
        db.commit()
