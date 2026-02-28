from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt


def jwt_secret() -> str:
    return os.environ.get("JWT_SECRET") or (_ for _ in ()).throw(RuntimeError, "JWT_SECRET is required")


def jwt_ttl_minutes() -> int:
    try:
        return int(os.environ.get("JWT_TTL_MINUTES", "60"))
    except ValueError:
        return 60


def refresh_token_ttl_days() -> int:
    try:
        return int(os.environ.get("JWT_REFRESH_TTL_DAYS", "7"))
    except ValueError:
        return 7


def create_access_token(*, subject: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=jwt_ttl_minutes())
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=refresh_token_ttl_days())
