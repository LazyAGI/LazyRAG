"""Bootstrap admin user and migrate users.role_id -> users.role_name if needed."""
from __future__ import annotations

import os
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db import engine
from models import User
from auth_service import hash_password


def _users_table_has_role_id() -> bool:
    if "postgresql" not in (os.environ.get("DATABASE_URL") or ""):
        return False
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'users'"
            )
        )
        cols = {row[0] for row in r}
    return "role_id" in cols


def _roles_table_exists() -> bool:
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'roles'"
            )
        )
        return r.scalar() is not None


def _migrate_users_role_id_to_role_name() -> None:
    """Migrate users.role_id to users.role_name. Backfill from roles if that table exists."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role_name VARCHAR(64)"))
        if _roles_table_exists():
            conn.execute(text(
                "UPDATE users u SET role_name = (SELECT name FROM roles r WHERE r.id = u.role_id LIMIT 1) "
                "WHERE u.role_id IS NOT NULL"
            ))
        conn.execute(text("UPDATE users SET role_name = 'user' WHERE role_name IS NULL"))
        conn.execute(text("ALTER TABLE users ALTER COLUMN role_name SET NOT NULL"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS role_id"))
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_role_id"))
    except Exception:
        pass


def bootstrap(db: Session) -> None:
    if _users_table_has_role_id():
        _migrate_users_role_id_to_role_name()

    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return
    if db.scalar(select(User).where(User.username == username)):
        return
    admin_user = User(
        username=username,
        password_hash=hash_password(password),
        role_name="admin",
    )
    db.add(admin_user)
    db.commit()
