"""Refresh token storage: Redis, key=token_hash, value contains user_id and expiry, TTL=refresh validity."""
import json
import logging
import time
import uuid

from core.redis_client import redis_client
from core.security import refresh_token_ttl_seconds

logger = logging.getLogger('auth-service')

KEY_PREFIX = 'auth:rt:'


def _key(token_hash: str) -> str:
    return f'{KEY_PREFIX}{token_hash}'


def set_refresh_token(token_hash: str, user_id: uuid.UUID) -> None:
    """Store refresh token with TTL and embedded expiry metadata."""
    r = redis_client()
    key = _key(token_hash)
    ttl = refresh_token_ttl_seconds()
    payload = {
        'user_id': str(user_id),
        'expires_at': int(time.time()) + ttl,
    }
    r.set(key, json.dumps(payload), ex=ttl)


def get_user_id_by_token(token_hash: str) -> uuid.UUID | None:
    """Return user_id for token_hash, or None if missing/expired/invalid."""
    r = redis_client()
    key = _key(token_hash)
    val = r.get(key)
    if val is None:
        return None

    try:
        payload = json.loads(val)
    except (TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    expires_at = payload.get('expires_at')
    if not isinstance(expires_at, (int, float)):
        return None
    if expires_at <= time.time():
        delete_refresh_token(token_hash)
        return None

    raw_user_id = payload.get('user_id')
    try:
        return uuid.UUID(raw_user_id)
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
