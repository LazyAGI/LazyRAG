"""
Login failure rate limiting (deny login for a period after N consecutive failures on the same account)
"""
import time
import redis

from core.redis_client import redis_client

LOGIN_MAX_ATTEMPTS = 3
LOGIN_TIME_WINDOW_SECONDS = 60


class LoginRateLimiter:
    """Per-user login failure rate limiter (Redis ZSET sliding window)"""

    def __init__(
        self,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        time_window_seconds: int = LOGIN_TIME_WINDOW_SECONDS,
        *,
        key_prefix: str = 'login_rate_limiter',
    ):
        self._max_attempts = max_attempts
        self._time_window = time_window_seconds
        self._key_prefix = key_prefix

    def is_limited(self, user_id: int | str) -> bool:
        """Return True when failures for the same user reach the limit within the time window."""
        try:
            r = redis_client()
            key = f'{self._key_prefix}:{user_id}'
            now = int(time.time())
            window_start_time = now - self._time_window

            pipe = r.pipeline()
            pipe.zremrangebyscore(key, '-inf', window_start_time)
            pipe.zcard(key)
            _, attempts = pipe.execute()

            try:
                return int(attempts) >= self._max_attempts
            except (TypeError, ValueError):
                return False
        except redis.RedisError:
            # Do not block login when Redis is unavailable (only lose rate-limit protection)
            return False

    def record_failure(self, user_id: int | str) -> None:
        """Record one login failure."""
        try:
            r = redis_client()
            key = f'{self._key_prefix}:{user_id}'
            now = int(time.time())

            pipe = r.pipeline()
            pipe.zadd(key, {now: now})
            pipe.expire(key, self._time_window * 2)
            pipe.execute()
        except redis.RedisError:
            return


login_rate_limiter = LoginRateLimiter()
