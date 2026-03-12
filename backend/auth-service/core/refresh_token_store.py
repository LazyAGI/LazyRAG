"""Refresh token storage: Redis, key=token_hash, value=user_id (UUID string), TTL=refresh validity."""
import logging
import uuid

from core.redis_client import redis_client
from core.security import refresh_token_ttl_seconds

logger = logging.getLogger('auth-service')

KEY_PREFIX = 'auth:rt:'


def _key(token_hash: str) -> str:
    return f'{KEY_PREFIX}{token_hash}'


def set_refresh_token(token_hash: str, user_id: uuid.UUID) -> None:
    """Store refresh token; TTL expires automatically."""
    r = redis_client()
    key = _key(token_hash)
    ttl = refresh_token_ttl_seconds()
    r.set(key, str(user_id), ex=ttl)


def get_user_id_by_token(token_hash: str) -> uuid.UUID | None:
    """Return user_id (UUID) for token_hash, or None if missing/expired."""
    r = redis_client()
    key = _key(token_hash)
    val = r.get(key)
    if val is None:
        return None
    try:
        return uuid.UUID(val)
    except (TypeError, ValueError):
        return None


def delete_refresh_token(token_hash: str) -> None:
    """使该 refresh token 失效（登出或刷新时删旧 token）。"""
    r = redis_client()
    key = _key(token_hash)
    try:
        r.delete(key)
    except Exception as e:
        logger.warning('Redis delete refresh_token key failed: %s', e)
