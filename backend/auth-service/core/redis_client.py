import os

import redis


_CLIENT: redis.Redis | None = None


def redis_url() -> str:
    url = (os.environ.get('LAZYRAG_REDIS_URL') or '').strip()
    if url:
        return url
    return 'redis://localhost:6379/0'


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
