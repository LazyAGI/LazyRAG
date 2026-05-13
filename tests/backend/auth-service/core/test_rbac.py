from types import SimpleNamespace

import pytest

import core.rbac as rbac
from core.errors import AppException


def test_permission_required_without_permissions_returns_original_function():
    def endpoint():
        return 'ok'

    wrapped = rbac.permission_required()(endpoint)

    assert wrapped is endpoint
    assert wrapped() == 'ok'
    assert endpoint.__required_permissions__ == set()


def test_permission_required_allows_system_admin_without_permission_lookup(monkeypatch):
    def endpoint(user):
        return 'ok'

    user = SimpleNamespace(role=SimpleNamespace(name='system-admin'))
    monkeypatch.setattr(rbac, 'get_effective_permission_codes', lambda row: (_ for _ in ()).throw(AssertionError))

    assert rbac.permission_required('user.admin')(endpoint)(user) == 'ok'


def test_permission_required_allows_when_user_has_any_required_permission(monkeypatch):
    def endpoint(user):
        return 'ok'

    user = SimpleNamespace(role=SimpleNamespace(name='member'))
    monkeypatch.setattr(rbac, 'get_effective_permission_codes', lambda row: {'user.read'})

    assert rbac.permission_required('user.read', 'user.write')(endpoint)(user) == 'ok'


def test_permission_required_rejects_missing_user_or_permission(monkeypatch):
    def endpoint(user=None):
        return 'ok'

    with pytest.raises(AppException) as unauthorized:
        rbac.permission_required('user.read')(endpoint)()
    assert unauthorized.value.code == 1000301

    monkeypatch.setattr(rbac, 'get_effective_permission_codes', lambda row: set())
    user = SimpleNamespace(role=SimpleNamespace(name='member'))
    with pytest.raises(AppException) as forbidden:
        rbac.permission_required('user.read')(endpoint)(user)
    assert forbidden.value.code == 1000302


def test_permission_required_finds_user_from_kwargs(monkeypatch):
    def endpoint(*, actor=None):
        return 'ok'

    user = SimpleNamespace(role=SimpleNamespace(name='member'))
    monkeypatch.setattr(rbac, 'get_effective_permission_codes', lambda row: {'user.read'})

    result = rbac.permission_required('user.read')(endpoint)(actor=user)

    assert result == 'ok'
