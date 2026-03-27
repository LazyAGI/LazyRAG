import os
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from models import RolePermission
from repositories import PermissionGroupRepository, RoleRepository, UserRepository
from services.auth_service import auth_service


def _load_yaml() -> dict:
    path = Path(__file__).resolve().parent / 'permission_groups.yaml'
    try:
        with open(path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data or {}
    except Exception:
        return {}


def _normalize_codes(values: list[str] | None) -> list[str]:
    """Remove empty values and duplicates while preserving order, so bootstrap logic remains repeatable."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        code = (value or '').strip()
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return normalized


def _load_permission_groups_yaml() -> list[str]:
    data = _load_yaml()
    return _normalize_codes(data.get('permission_groups', []) or [])


def _load_default_user_role_permissions() -> list[str]:
    """Default permission codes for the built-in user role, loaded from permission_groups.yaml."""
    data = _load_yaml()
    return _normalize_codes(data.get('default_user_role_permissions', []) or [])


def _code_to_module_action(code: str) -> tuple[str, str]:
    """Parse module and action from a permission code, e.g. user.read -> ('user', 'read')"""
    parts = (code or '').strip().split('.', 1)
    return (parts[0] or '', parts[1] if len(parts) > 1 else '')


def bootstrap(db: Session) -> None:
    configured_permission_codes = set(_load_permission_groups_yaml())
    for code in configured_permission_codes:
        if not PermissionGroupRepository.get_by_code(db, code):
            module, action = _code_to_module_action(code)
            PermissionGroupRepository.create(db, code=code, description='', module=module, action=action)

    all_groups = {g.code: g.id for g in PermissionGroupRepository.list_all_ordered(db)}

    system_admin_role = RoleRepository.get_by_name(db, 'system-admin')
    if not system_admin_role:
        system_admin_role = RoleRepository.create(db, 'system-admin', built_in=True)
    user_role = RoleRepository.get_by_name(db, 'user')
    if not user_role:
        user_role = RoleRepository.create(db, 'user', built_in=True)

    for code in configured_permission_codes:
        pg_id = all_groups.get(code)
        if not pg_id:
            continue
        exists = db.query(RolePermission).filter_by(
            role_id=system_admin_role.id,
            permission_group_id=pg_id,
        ).first()
        if not exists:
            db.add(RolePermission(role_id=system_admin_role.id, permission_group_id=pg_id))

    for perm_name in _load_default_user_role_permissions():
        pg_id = all_groups.get(perm_name)
        if not pg_id:
            continue
        exists = db.query(RolePermission).filter_by(
            role_id=user_role.id,
            permission_group_id=pg_id,
        ).first()
        if not exists:
            db.add(RolePermission(role_id=user_role.id, permission_group_id=pg_id))
    db.commit()

    username = os.environ.get('LAZYRAG_BOOTSTRAP_ADMIN_USERNAME', 'system-admin').strip() or 'system-admin'
    password = os.environ.get('LAZYRAG_BOOTSTRAP_ADMIN_PASSWORD', '123456').strip() or '123456'
    if UserRepository.get_by_username(db, username):
        return
    UserRepository.create(
        db,
        username=username,
        password_hash=auth_service.hash_password(password),
        role_id=system_admin_role.id,
        tenant_id='',
        disabled=False,
    )
