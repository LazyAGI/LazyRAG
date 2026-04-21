import uuid
from types import SimpleNamespace

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError

import core.deps as deps
from core.errors import AppException


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_user_id_from_token_decodes_uuid(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(deps, 'jwt_secret', lambda: 'secret')
    monkeypatch.setattr(deps.jwt, 'decode', lambda token, secret, algorithms: {'sub': str(user_id)})

    assert deps._user_id_from_token('token') == user_id


def test_user_id_from_token_rejects_invalid_token_or_subject(monkeypatch):
    monkeypatch.setattr(deps, 'jwt_secret', lambda: 'secret')
    monkeypatch.setattr(deps.jwt, 'decode', lambda token, secret, algorithms: (_ for _ in ()).throw(JWTError()))
    with pytest.raises(AppException) as bad_token:
        deps._user_id_from_token('token')
    assert bad_token.value.code == 1000301

    monkeypatch.setattr(deps.jwt, 'decode', lambda token, secret, algorithms: {})
    with pytest.raises(AppException) as missing_sub:
        deps._user_id_from_token('token')
    assert missing_sub.value.code == 1000301

    monkeypatch.setattr(deps.jwt, 'decode', lambda token, secret, algorithms: {'sub': 'bad-uuid'})
    with pytest.raises(AppException) as bad_sub:
        deps._user_id_from_token('token')
    assert bad_sub.value.code == 1000301


def test_current_user_id_requires_credentials(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(deps, '_user_id_from_token', lambda token: user_id)

    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials='token')
    assert deps.current_user_id(credentials) == user_id

    with pytest.raises(AppException) as exc:
        deps.current_user_id(None)
    assert exc.value.code == 1000301


def test_current_user_loads_enabled_user(monkeypatch):
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, disabled=False)
    monkeypatch.setattr(deps, 'SessionLocal', lambda: _Session())
    monkeypatch.setattr(deps.UserRepository, 'get_by_id', lambda db, uid, **kwargs: user)

    assert deps.current_user(user_id) is user


def test_current_user_rejects_missing_or_disabled_user(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(deps, 'SessionLocal', lambda: _Session())
    monkeypatch.setattr(deps.UserRepository, 'get_by_id', lambda db, uid, **kwargs: None)
    with pytest.raises(AppException) as missing:
        deps.current_user(user_id)
    assert missing.value.code == 1000301

    monkeypatch.setattr(
        deps.UserRepository,
        'get_by_id',
        lambda db, uid, **kwargs: SimpleNamespace(disabled=True),
    )
    with pytest.raises(AppException) as disabled:
        deps.current_user(user_id)
    assert disabled.value.code == 1000106


def test_require_admin_allows_only_system_admin():
    admin = SimpleNamespace(role=SimpleNamespace(name='system-admin'))
    member = SimpleNamespace(role=SimpleNamespace(name='member'))

    assert deps.require_admin(admin) is admin
    with pytest.raises(AppException) as exc:
        deps.require_admin(member)
    assert exc.value.code == 1000303
