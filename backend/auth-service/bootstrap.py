"""Load permission groups from YAML, create default roles and admin user."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_service import hash_password
from models import PermissionGroup, Role, RolePermission, User


def _load_permission_groups_yaml() -> list[str]:
    """Load permission group names from permission_groups.yaml (default source)."""
    path = Path(__file__).resolve().parent / "permission_groups.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return list(data.get("permission_groups", []) or [])
    except Exception:
        return []


def bootstrap(db: Session) -> None:
    names = _load_permission_groups_yaml()
    for name in names:
        existing = db.scalar(select(PermissionGroup).where(PermissionGroup.name == name))
        if not existing:
            db.add(PermissionGroup(name=name))
    db.commit()

    all_groups = {row.name: row.id for row in db.scalars(select(PermissionGroup)).all()}

    admin_role = db.scalar(select(Role).where(Role.name == "admin"))
    if not admin_role:
        admin_role = Role(name="admin", built_in=True)
        db.add(admin_role)
        db.flush()
    user_role = db.scalar(select(Role).where(Role.name == "user"))
    if not user_role:
        user_role = Role(name="user", built_in=True)
        db.add(user_role)
        db.flush()
    db.commit()

    for name, pg_id in all_groups.items():
        exists = db.scalar(
            select(RolePermission).where(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_group_id == pg_id,
            )
        )
        if not exists:
            db.add(RolePermission(role_id=admin_role.id, permission_group_id=pg_id))

    for perm_name in ("user.read", "document.read"):
        if perm_name in all_groups:
            exists = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == user_role.id,
                    RolePermission.permission_group_id == all_groups[perm_name],
                )
            )
            if not exists:
                db.add(RolePermission(role_id=user_role.id, permission_group_id=all_groups[perm_name]))
    db.commit()

    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return
    if db.scalar(select(User).where(User.username == username)):
        return
    admin_user = User(
        username=username,
        password_hash=hash_password(password),
        role_id=admin_role.id,
    )
    db.add(admin_user)
    db.commit()
