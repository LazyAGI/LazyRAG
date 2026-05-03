import redis

import core.rate_limit as rate_limit


class _Pipeline:
    def __init__(self, result=None, fail=False):
        self.calls = []
        self.result = result or []
        self.fail = fail

    def zremrangebyscore(self, *args):
        self.calls.append(('zremrangebyscore', args))
        return self

    def zcard(self, *args):
        self.calls.append(('zcard', args))
        return self

    def zadd(self, *args):
        self.calls.append(('zadd', args))
        return self

    def expire(self, *args):
        self.calls.append(('expire', args))
        return self

    def execute(self):
        if self.fail:
            raise redis.RedisError('redis down')
        return self.result


class _Redis:
    def __init__(self, pipeline):
        self._pipeline = pipeline

    def pipeline(self):
        return self._pipeline


def test_is_limited_uses_sliding_window_and_threshold(monkeypatch):
    pipe = _Pipeline(result=[1, 3])
    monkeypatch.setattr(rate_limit.time, 'time', lambda: 100)
    monkeypatch.setattr(rate_limit, 'redis_client', lambda: _Redis(pipe))
    limiter = rate_limit.LoginRateLimiter(max_attempts=3, time_window_seconds=60, key_prefix='login')

    assert limiter.is_limited('alice') is True
    assert pipe.calls == [
        ('zremrangebyscore', ('login:alice', '-inf', 40)),
        ('zcard', ('login:alice',)),
    ]


def test_is_limited_returns_false_for_bad_counts_or_redis_errors(monkeypatch):
    pipe = _Pipeline(result=[1, 'bad'])
    monkeypatch.setattr(rate_limit, 'redis_client', lambda: _Redis(pipe))
    assert rate_limit.LoginRateLimiter().is_limited('alice') is False

    failing = _Pipeline(fail=True)
    monkeypatch.setattr(rate_limit, 'redis_client', lambda: _Redis(failing))
    assert rate_limit.LoginRateLimiter().is_limited('alice') is False


def test_record_failure_records_timestamp_and_expiry(monkeypatch):
    pipe = _Pipeline(result=[True, True])
    monkeypatch.setattr(rate_limit.time, 'time', lambda: 123)
    monkeypatch.setattr(rate_limit, 'redis_client', lambda: _Redis(pipe))
    limiter = rate_limit.LoginRateLimiter(time_window_seconds=60, key_prefix='login')

    limiter.record_failure('alice')

    assert pipe.calls == [
        ('zadd', ('login:alice', {123: 123})),
        ('expire', ('login:alice', 120)),
    ]


def test_record_failure_ignores_redis_errors(monkeypatch):
    failing = _Pipeline(fail=True)
    monkeypatch.setattr(rate_limit, 'redis_client', lambda: _Redis(failing))

    rate_limit.LoginRateLimiter().record_failure('alice')
