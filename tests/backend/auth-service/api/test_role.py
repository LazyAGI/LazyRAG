import uuid

import pytest

import api.role as role_api
from core.errors import AppException
from schemas.role import RoleCreateBody, RolePermissionsBody


def _call(fn, *args, **kwargs):
    return getattr(fn, '__wrapped__', fn)(*args, **kwargs)


def test_parse_role_id_returns_uuid_and_rejects_invalid_value():
    value = str(uuid.uuid4())

    assert role_api._parse_role_id(value) == uuid.UUID(value)
    with pytest.raises(AppException) as exc:
        role_api._parse_role_id('bad-role')
    assert exc.value.code == 1000403


def test_list_permission_groups_and_roles_delegate_to_service(monkeypatch):
    monkeypatch.setattr(role_api.role_service, 'list_permission_groups', lambda: ['pg'])
    monkeypatch.setattr(role_api.role_service, 'list_roles', lambda: ['role'])

    assert _call(role_api.list_permission_groups, object()) == ['pg']
    assert _call(role_api.list_roles, object()) == ['role']


def test_create_role_strips_name(monkeypatch):
    calls = []
    monkeypatch.setattr(role_api.role_service, 'create_role', lambda name: calls.append(name) or {'name': name})

    result = _call(role_api.create_role, RoleCreateBody(name='  manager  '), object())

    assert result == {'name': 'manager'}
    assert calls == ['manager']


def test_delete_role_converts_id(monkeypatch):
    role_id = uuid.uuid4()
    calls = []
    monkeypatch.setattr(role_api.role_service, 'delete_role', lambda rid: calls.append(rid))

    assert _call(role_api.delete_role, str(role_id), object()) == {'ok': True}
    assert calls == [role_id]


def test_get_and_set_role_permissions(monkeypatch):
    role_id = uuid.uuid4()
    calls = []
    monkeypatch.setattr(
        role_api.role_service,
        'get_role_permissions',
        lambda rid: calls.append(('get', rid)) or ['user.read'],
    )
    monkeypatch.setattr(
        role_api.role_service,
        'set_role_permissions',
        lambda rid, groups: calls.append(('set', rid, groups)),
    )

    assert _call(role_api.get_role_permissions, str(role_id), object()) == {
        'role_id': str(role_id),
        'permission_groups': ['user.read'],
    }
    assert _call(
        role_api.set_role_permissions,
        str(role_id),
        RolePermissionsBody(permission_groups=['user.read', 'user.write']),
        object(),
    ) == {'ok': True}
    assert calls == [
        ('get', role_id),
        ('set', role_id, ['user.read', 'user.write']),
    ]
