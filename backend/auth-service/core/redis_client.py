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
        # 读写超时：每次操作的超时时间（秒）
        # 超时后连接会被标记为不可用，配合 retry_on_error 会重建连接并重试
        socket_timeout=5,
        # 健康检查间隔（秒）：定期检查连接健康，发现问题时从连接池移除
        # 设置为30秒，既能及时发现问题，又不会过于频繁
        health_check_interval=30,
        # 遇到以下错误时自动重试（会重建连接并重试命令）：
        # - ReadOnlyError: 主从切换时，旧连接指向从节点会返回此错误（最关键）
        # - ConnectionError: 连接错误时重试
        # - TimeoutError: 超时错误时重试
        retry_on_error=[
            redis.exceptions.ReadOnlyError,  # 主从切换场景的关键配置
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
        ],
        # 连接池配置
        max_connections=50,
    )
    return _CLIENT
