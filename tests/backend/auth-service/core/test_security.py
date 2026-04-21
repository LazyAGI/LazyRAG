import hashlib
from datetime import datetime, timezone

import pytest
from jose import jwt

import core.security as security


def test_jwt_secret_requires_env(monkeypatch):
    monkeypatch.delenv('LAZYRAG_JWT_SECRET', raising=False)

    with pytest.raises(RuntimeError, match='LAZYRAG_JWT_SECRET is required'):
        security.jwt_secret()


def test_env_int_uses_default_for_missing_or_invalid_value(monkeypatch):
    monkeypatch.delenv('INT_ENV', raising=False)
    assert security._env_int('INT_ENV', 7) == 7

    monkeypatch.setenv('INT_ENV', 'bad')
    assert security._env_int('INT_ENV', 7) == 7

    monkeypatch.setenv('INT_ENV', '9')
    assert security._env_int('INT_ENV', 7) == 9


def test_ttl_helpers_read_env(monkeypatch):
    monkeypatch.setenv('LAZYRAG_JWT_TTL_MINUTES', '2')
    monkeypatch.setenv('LAZYRAG_JWT_REFRESH_TTL_DAYS', '3')

    assert security.jwt_ttl_minutes() == 2
    assert security.jwt_ttl_seconds() == 120
    assert security.refresh_token_ttl_days() == 3
    assert security.refresh_token_ttl_seconds() == 259200


def test_create_access_token_contains_expected_claims(monkeypatch):
    monkeypatch.setenv('LAZYRAG_JWT_SECRET', 'test-secret')
    monkeypatch.setenv('LAZYRAG_JWT_TTL_MINUTES', '5')

    token = security.create_access_token(
        subject='user-1',
        role='system-admin',
        tenant_id='tenant-a',
        username='alice',
        jti='jti-1',
    )
    payload = jwt.decode(token, 'test-secret', algorithms=['HS256'])

    assert payload['sub'] == 'user-1'
    assert payload['user_id'] == 'user-1'
    assert payload['role'] == 'system-admin'
    assert payload['user_type'] == 'system-admin'
    assert payload['tenant_id'] == 'tenant-a'
    assert payload['tenant_code'] == 'default'
    assert payload['username'] == 'alice'
    assert payload['jti'] == 'jti-1'
    assert payload['exp'] > payload['iat']


def test_token_generators_and_hash(monkeypatch):
    monkeypatch.setattr(security.secrets, 'token_urlsafe', lambda size: f'url-{size}')
    monkeypatch.setattr(security.secrets, 'token_hex', lambda size: f'hex-{size}')

    assert security.generate_refresh_token() == 'url-32'
    assert security.generate_jti() == 'hex-16'
    assert security.hash_refresh_token('refresh-token') == hashlib.sha256(b'refresh-token').hexdigest()


def test_refresh_token_expires_at_uses_refresh_ttl(monkeypatch):
    class FakeDatetime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(security, 'datetime', FakeDatetime)
    monkeypatch.setenv('LAZYRAG_JWT_REFRESH_TTL_DAYS', '2')

    assert security.refresh_token_expires_at() == datetime(2026, 1, 3, tzinfo=timezone.utc)
