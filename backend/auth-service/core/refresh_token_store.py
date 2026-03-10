"""Refresh token 存储：使用 Redis，key 为 token_hash，value 为 user_id，TTL 与 refresh 有效期一致。"""
import logging

from core.redis_client import redis_client
from core.security import refresh_token_ttl_seconds

logger = logging.getLogger('auth-service')

KEY_PREFIX = 'auth:rt:'


def _key(token_hash: str) -> str:
    return f'{KEY_PREFIX}{token_hash}'


def set_refresh_token(token_hash: str, user_id: int) -> None:
    """写入 refresh token，TTL 到期自动失效。"""
    r = redis_client()
    key = _key(token_hash)
    ttl = refresh_token_ttl_seconds()
    r.set(key, str(user_id), ex=ttl)


def get_user_id_by_token(token_hash: str) -> int | None:
    """根据 token_hash 查 user_id，不存在或已过期返回 None。"""
    r = redis_client()
    key = _key(token_hash)
    val = r.get(key)
    if val is None:
        return None
    try:
        return int(val)
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
