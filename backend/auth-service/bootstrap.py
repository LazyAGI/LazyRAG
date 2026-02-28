"""Load built-in permission groups from YAML and bootstrap roles + admin user."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db import engine
from models import PermissionGroup, Role, RolePermission, User
from auth_service import hash_password


# Fallback if YAML is missing (e.g. wrong cwd in container)
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


def _users_table_has_old_schema() -> bool:
    """True if users has 'role' column and no 'role_id' (pre-permission schema)."""
    if "postgresql" not in (os.environ.get("DATABASE_URL") or ""):
        return False
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'users'"
            )
        )
        cols = {row[0] for row in r}
    return "role" in cols and "role_id" not in cols


def _migrate_users_to_role_id() -> None:
    """Migrate users.role (string) to users.role_id (FK). Run only for PostgreSQL with old schema."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER"))
        conn.execute(text("UPDATE users u SET role_id = (SELECT id FROM roles r WHERE r.name = u.role LIMIT 1) WHERE u.role_id IS NULL"))
        conn.execute(text("UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'user' LIMIT 1) WHERE role_id IS NULL"))
        conn.execute(text("ALTER TABLE users ALTER COLUMN role_id SET NOT NULL"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS role"))
        try:
            conn.execute(text(
                "ALTER TABLE users ADD CONSTRAINT fk_users_role_id "
                "FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT"
            ))
        except Exception:
            pass


def bootstrap(db: Session) -> None:
    """Create permission groups from YAML (or fallback), built-in roles, and default admin user."""
    names = _load_permission_groups_yaml()

    # Upsert permission groups
    for name in names:
        existing = db.scalar(select(PermissionGroup).where(PermissionGroup.name == name))
        if not existing:
            db.add(PermissionGroup(name=name))
    db.commit()

    # Fetch all permission group ids by name
    all_groups = {row.name: row.id for row in db.scalars(select(PermissionGroup)).all()}

    # Create built-in roles
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

    # Assign all permission groups to admin
    for name, pg_id in all_groups.items():
        exists = db.scalar(
            select(RolePermission).where(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_group_id == pg_id,
            )
        )
        if not exists:
            db.add(RolePermission(role_id=admin_role.id, permission_group_id=pg_id))

    # Assign user.read, document.read to built-in "user" role (optional: add more as needed)
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

    # Migrate old users.role (string) to users.role_id if needed (upgrade from pre-permission schema)
    if _users_table_has_old_schema():
        _migrate_users_to_role_id()

    # Bootstrap admin user (re-query role id; admin_role may be expired after earlier commits)
    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return
    if db.scalar(select(User).where(User.username == username)):
        return
    admin_role_id = db.scalar(select(Role.id).where(Role.name == "admin"))
    if not admin_role_id:
        raise RuntimeError("Bootstrap: admin role not found")
    admin_user = User(
        username=username,
        password_hash=hash_password(password),
        role_id=admin_role_id,
    )
    db.add(admin_user)
    db.commit()
