import os

import redis


_CLIENT: redis.Redis | None = None
REDIS_URL_ENV = 'LAZYRAG_REDIS_URL'


def redis_url() -> str:
    url = (os.environ.get(REDIS_URL_ENV) or '').strip()
    if not url:
        raise RuntimeError(f'{REDIS_URL_ENV} is required for auth-service Redis features')
    return url


def redis_client() -> redis.Redis:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    url = redis_url()
    _CLIENT = redis.Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
        retry_on_error=[
            redis.exceptions.ReadOnlyError,
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
        ],
        max_connections=50,
    )
    return _CLIENT
