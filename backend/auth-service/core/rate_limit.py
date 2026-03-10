"""
登录失败频率限制(同一账号连续失败N次后一段时间内拒绝登录)
"""
import time
import redis

from core.redis_client import redis_client

LOGIN_MAX_ATTEMPTS = 3
LOGIN_TIME_WINDOW_SECONDS = 60


class LoginRateLimiter:
    """按用户维度的登录失败限流器(Redis ZSET 滑动窗口)"""

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
        """同一用户在时间窗口内失败次数已达上限则返回 True。"""
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
            # Redis 不可用时不阻断登录流程(仅失去限流保护)
            return False

    def record_failure(self, user_id: int | str) -> None:
        """记录一次登录失败。"""
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
