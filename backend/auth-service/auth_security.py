from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt


def jwt_secret() -> str:
    s = os.environ.get('JWT_SECRET')
    if not s:
        raise RuntimeError('JWT_SECRET is required')
    return s


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def jwt_ttl_minutes() -> int:
    return _env_int('JWT_TTL_MINUTES', 60)


def refresh_token_ttl_days() -> int:
    return _env_int('JWT_REFRESH_TTL_DAYS', 7)


def create_access_token(*, subject: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=jwt_ttl_minutes())
    payload: dict[str, Any] = {
        'sub': subject,
        'role': role,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm='HS256')


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def refresh_token_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=refresh_token_ttl_days())
