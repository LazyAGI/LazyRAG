import pytest

import core.redis_client as redis_client_module


def test_redis_url_requires_env(monkeypatch):
    monkeypatch.delenv(redis_client_module.REDIS_URL_ENV, raising=False)

    with pytest.raises(RuntimeError, match='LAZYRAG_REDIS_URL is required'):
        redis_client_module.redis_url()


def test_redis_url_strips_env_value(monkeypatch):
    monkeypatch.setenv(redis_client_module.REDIS_URL_ENV, ' redis://localhost:6379/0 ')

    assert redis_client_module.redis_url() == 'redis://localhost:6379/0'


def test_redis_client_builds_and_caches_client(monkeypatch):
    seen = {}

    class FakeRedis:
        @staticmethod
        def from_url(url, **kwargs):
            seen['url'] = url
            seen['kwargs'] = kwargs
            return {'client': url}

    monkeypatch.setattr(redis_client_module, '_CLIENT', None)
    monkeypatch.setattr(redis_client_module, 'redis', FakeRedis)
    monkeypatch.setenv(redis_client_module.REDIS_URL_ENV, 'redis://localhost:6379/1')

    client = redis_client_module.redis_client()

    assert client == {'client': 'redis://localhost:6379/1'}
    assert redis_client_module.redis_client() is client
    assert seen['url'] == 'redis://localhost:6379/1'
    assert seen['kwargs']['decode_responses'] is True
    assert seen['kwargs']['socket_connect_timeout'] == 5
    assert seen['kwargs']['socket_timeout'] == 5
    assert seen['kwargs']['health_check_interval'] == 30
    assert seen['kwargs']['max_connections'] == 50
