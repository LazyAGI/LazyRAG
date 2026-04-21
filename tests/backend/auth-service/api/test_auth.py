import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import api.auth as auth_api
from core.errors import AppException
from schemas.auth import (
    ChangePasswordBody,
    LoginBody,
    LogoutBody,
    RefreshBody,
    RegisterBody,
    UpdateMeBody,
)


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True


def test_default_role_id_returns_user_role_or_raises(monkeypatch):
    role_id = uuid.uuid4()
    monkeypatch.setattr(auth_api.RoleRepository, 'get_by_name', lambda session, name: SimpleNamespace(id=role_id))
    assert auth_api._default_role_id(object()) == role_id

    monkeypatch.setattr(auth_api.RoleRepository, 'get_by_name', lambda session, name: None)
    with pytest.raises(AppException) as exc:
        auth_api._default_role_id(object())
    assert exc.value.code == 1000501


def test_run_alembic_upgrade_skips_when_ini_missing(monkeypatch):
    class MissingPath:
        def __init__(self, value):
            self.value = value

        def resolve(self):
            return self

        @property
        def parent(self):
            return self

        def __truediv__(self, other):
            return self

        def exists(self):
            return False

        def __str__(self):
            return '/missing/alembic.ini'

    monkeypatch.setattr(auth_api, 'Path', MissingPath)
    auth_api._run_alembic_upgrade()


def test_health_returns_status_and_timestamp(monkeypatch):
    monkeypatch.setattr(auth_api.time, 'time', lambda: 123.5)

    assert auth_api.health() == {'status': 'ok', 'timestamp': 123.5}


def test_register_validates_confirmation_and_delegates(monkeypatch):
    user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id, role_id=role_id, tenant_id='tenant-a')
    session = _Session()
    calls = []
    monkeypatch.setattr(auth_api, 'SessionLocal', lambda: session)
    monkeypatch.setattr(auth_api, '_default_role_id', lambda db: role_id)
    monkeypatch.setattr(
        auth_api.auth_service,
        'register_user',
        lambda **kwargs: calls.append(kwargs) or fake_user,
    )
    monkeypatch.setattr(auth_api.RoleRepository, 'get_by_id', lambda db, rid: SimpleNamespace(name='user'))

    result = auth_api.register(
        RegisterBody(
            username=' alice ',
            password=' secret ',
            confirm_password='secret',
            email='alice@example.test',
            tenant_id='tenant-a',
        )
    )

    assert result == {'success': True, 'user_id': str(user_id), 'tenant_id': 'tenant-a', 'role': 'user'}
    assert calls[0]['username'] == 'alice'
    assert calls[0]['password'] == 'secret'
    assert calls[0]['role_id'] == role_id

    with pytest.raises(AppException) as exc:
        auth_api.register(RegisterBody(username='a', password='one', confirm_password='two'))
    assert exc.value.code == 1000204


def test_login_requires_username_and_password(monkeypatch):
    with pytest.raises(AppException) as username_exc:
        auth_api.login(LoginBody(username=' ', password='secret'))
    with pytest.raises(AppException) as password_exc:
        auth_api.login(LoginBody(username='alice', password=''))

    assert username_exc.value.code == 1000201
    assert password_exc.value.code == 1000202


def test_login_authenticates_and_stores_refresh_token(monkeypatch):
    user_id = uuid.uuid4()
    session = _Session()
    user = SimpleNamespace(id=user_id)
    loaded = SimpleNamespace(
        id=user_id,
        username='alice',
        tenant_id='tenant-a',
        role=SimpleNamespace(name='user'),
    )
    stored = []
    monkeypatch.setattr(auth_api, 'SessionLocal', lambda: session)
    monkeypatch.setattr(auth_api.auth_service, 'authenticate_user', lambda **kwargs: user)
    monkeypatch.setattr(auth_api.UserRepository, 'get_by_id', lambda db, uid, load_role=False: loaded)
    monkeypatch.setattr(auth_api, 'create_access_token', lambda **kwargs: 'access-token')
    monkeypatch.setattr(auth_api, 'generate_jti', lambda: 'jti')
    monkeypatch.setattr(auth_api, 'generate_refresh_token', lambda: 'refresh-token')
    monkeypatch.setattr(auth_api, 'hash_refresh_token', lambda token: f'hash:{token}')
    monkeypatch.setattr(auth_api, 'set_refresh_token', lambda token_hash, uid: stored.append((token_hash, uid)))
    monkeypatch.setattr(auth_api, 'refresh_token_expires_at', lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(auth_api, 'jwt_ttl_seconds', lambda: 3600)

    result = auth_api.login(LoginBody(username=' alice ', password='secret'))

    assert result['access_token'] == 'access-token'
    assert result['refresh_token'] == 'refresh-token'
    assert result['role'] == 'user'
    assert result['tenant_id'] == 'tenant-a'
    assert stored == [('hash:refresh-token', user_id)]


def test_refresh_rotates_token_and_rejects_missing_or_unknown(monkeypatch):
    with pytest.raises(AppException) as missing:
        auth_api.refresh(RefreshBody(refresh_token=' '))
    assert missing.value.code == 1000203

    monkeypatch.setattr(auth_api, 'hash_refresh_token', lambda token: f'hash:{token}')
    monkeypatch.setattr(auth_api, 'get_user_id_by_token', lambda token_hash: None)
    with pytest.raises(AppException) as invalid:
        auth_api.refresh(RefreshBody(refresh_token='old'))
    assert invalid.value.code == 1000207


def test_me_update_change_password_and_logout(monkeypatch):
    user_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        username='alice',
        display_name='Alice',
        email='alice@example.test',
        disabled=False,
        role=SimpleNamespace(name='user'),
        tenant_id='tenant-a',
        password_hash='old-hash',
    )
    import core.permissions

    monkeypatch.setattr(core.permissions, 'get_effective_permission_codes', lambda row: {'user.read'})
    assert auth_api.me(user) == {
        'user_id': str(user_id),
        'username': 'alice',
        'display_name': 'Alice',
        'email': 'alice@example.test',
        'status': 'active',
        'role': 'user',
        'permissions': ['user.read'],
        'tenant_id': 'tenant-a',
    }

    session = _Session()
    row = SimpleNamespace(password_hash='old-hash', updated_pwd_time=None)
    deleted = []
    monkeypatch.setattr(auth_api, 'SessionLocal', lambda: session)
    monkeypatch.setattr(auth_api.UserRepository, 'update_profile', lambda db, uid, **kwargs: True)
    monkeypatch.setattr(auth_api.UserRepository, 'get_by_id', lambda db, uid: row)
    monkeypatch.setattr(auth_api.auth_service, 'verify_password', lambda plain, hashed: True)
    monkeypatch.setattr(auth_api.auth_service, 'validate_password', lambda plain: True)
    monkeypatch.setattr(auth_api.auth_service, 'hash_password', lambda plain: f'hash:{plain}')
    monkeypatch.setattr(auth_api, 'hash_refresh_token', lambda token: f'hash:{token}')
    monkeypatch.setattr(auth_api, 'delete_refresh_token', lambda token_hash: deleted.append(token_hash))

    assert auth_api.update_me(UpdateMeBody(display_name='A'), user) == {'success': True}
    assert auth_api.change_password(ChangePasswordBody(old_password='old', new_password='newpass'), user) == {'success': True}
    assert row.password_hash == 'hash:newpass'
    assert auth_api.logout(LogoutBody(refresh_token='refresh-token'), user) == {'success': True}
    assert deleted == ['hash:refresh-token']
