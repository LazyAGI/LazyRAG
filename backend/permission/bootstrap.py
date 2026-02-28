"""Load built-in permission groups from YAML and create default roles with permissions."""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import PermissionGroup, Role, RolePermission

BUILTIN_PERMISSION_GROUPS = [
    "user.read", "user.write", "document.read", "document.write", "qa.read",
]


def _load_permission_groups_yaml() -> list[str]:
    path = Path(__file__).resolve().parent / "permission_groups.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        names = list(data.get("permission_groups", []) or [])
    except Exception:
        names = []
    return names if names else BUILTIN_PERMISSION_GROUPS


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
