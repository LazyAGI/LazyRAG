import uuid
from types import SimpleNamespace

import pytest

import api.group as group_api
from core.errors import AppException
from schemas.group import (
    GroupAddUsersBody,
    GroupCreateBody,
    GroupMemberRoleBatchBody,
    GroupRemoveUsersBody,
    GroupUpdateBody,
)


def _call(fn, *args, **kwargs):
    return getattr(fn, '__wrapped__', fn)(*args, **kwargs)


def test_parse_group_and_user_ids_raise_expected_errors():
    group_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    assert group_api._parse_group_id(group_id) == uuid.UUID(group_id)
    assert group_api._parse_user_id(user_id) == uuid.UUID(user_id)
    with pytest.raises(AppException) as group_exc:
        group_api._parse_group_id('bad-group')
    with pytest.raises(AppException) as user_exc:
        group_api._parse_user_id('bad-user')
    assert group_exc.value.code == 1000402
    assert user_exc.value.code == 1000401


def test_list_groups_returns_pagination_payload(monkeypatch):
    monkeypatch.setattr(group_api.group_service, 'list_groups', lambda **kwargs: (['g1'], 3))

    result = _call(group_api.list_groups, object(), page=2, page_size=10, search='team', tenant_id='tenant-a')

    assert result == {'groups': ['g1'], 'total': 3, 'page': 2, 'page_size': 10}


def test_create_group_strips_name_and_uses_user_tenant(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), tenant_id='tenant-from-user')
    calls = []
    monkeypatch.setattr(group_api.group_service, 'create_group', lambda **kwargs: calls.append(kwargs) or 'group-id')

    result = _call(group_api.create_group, GroupCreateBody(group_name='  team  ', remark=None, tenant_id=None), user)

    assert result == {'group_id': 'group-id'}
    assert calls == [{
        'group_name': 'team',
        'tenant_id': 'tenant-from-user',
        'remark': '',
        'creator_user_id': user.id,
    }]


def test_create_group_rejects_empty_name():
    with pytest.raises(AppException) as exc:
        _call(group_api.create_group, GroupCreateBody(group_name='   '), SimpleNamespace(id=uuid.uuid4(), tenant_id='t'))

    assert exc.value.code == 1000404


def test_get_group_raises_when_service_returns_none(monkeypatch):
    group_id = uuid.uuid4()
    monkeypatch.setattr(group_api.group_service, 'get_group', lambda gid: None)

    with pytest.raises(AppException) as exc:
        _call(group_api.get_group, str(group_id), object())

    assert exc.value.code == 1000402


def test_group_crud_and_member_endpoints_delegate_to_service(monkeypatch):
    group_id = uuid.uuid4()
    user_ids = [uuid.uuid4(), uuid.uuid4()]
    operator = SimpleNamespace(id=uuid.uuid4())
    calls = []
    monkeypatch.setattr(group_api.group_service, 'get_group', lambda gid: calls.append(('get', gid)) or {'group_id': str(gid)})
    monkeypatch.setattr(group_api.group_service, 'update_group', lambda gid, **kwargs: calls.append(('update', gid, kwargs)))
    monkeypatch.setattr(group_api.group_service, 'delete_group', lambda gid: calls.append(('delete', gid)))
    monkeypatch.setattr(group_api.group_service, 'list_group_users', lambda gid: calls.append(('list_users', gid)) or ['u1'])
    monkeypatch.setattr(
        group_api.group_service,
        'add_group_users',
        lambda gid, uids, role, operator_id: calls.append(('add', gid, uids, role, operator_id)),
    )
    monkeypatch.setattr(
        group_api.group_service,
        'remove_group_users',
        lambda gid, uids: calls.append(('remove', gid, uids)),
    )
    monkeypatch.setattr(
        group_api.group_service,
        'set_member_roles_batch',
        lambda gid, uids, role: calls.append(('roles', gid, uids, role)),
    )

    assert _call(group_api.get_group, str(group_id), object()) == {'group_id': str(group_id)}
    assert _call(
        group_api.update_group,
        str(group_id),
        GroupUpdateBody(group_name='  renamed  ', remark='r', tenant_id='tenant-b'),
        object(),
    ) == {'ok': True}
    assert _call(group_api.delete_group, str(group_id), object()) == {'ok': True}
    assert _call(group_api.list_group_users, str(group_id), object()) == {'users': ['u1']}
    assert _call(
        group_api.add_group_users,
        str(group_id),
        GroupAddUsersBody(user_ids=[str(item) for item in user_ids], role='  owner  '),
        operator,
    ) == {'ok': True}
    assert _call(
        group_api.remove_group_users,
        str(group_id),
        GroupRemoveUsersBody(user_ids=[str(item) for item in user_ids]),
        object(),
    ) == {'ok': True}
    assert _call(
        group_api.set_member_roles_batch,
        str(group_id),
        GroupMemberRoleBatchBody(user_ids=[str(item) for item in user_ids], role='  member  '),
        object(),
    ) == {'ok': True}

    assert calls == [
        ('get', group_id),
        ('update', group_id, {'group_name': 'renamed', 'remark': 'r', 'tenant_id': 'tenant-b'}),
        ('delete', group_id),
        ('list_users', group_id),
        ('add', group_id, user_ids, 'owner', operator.id),
        ('remove', group_id, user_ids),
        ('roles', group_id, user_ids, 'member'),
    ]
