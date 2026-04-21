from types import SimpleNamespace

from core.permissions import get_effective_permission_codes


def _permission(code):
    return SimpleNamespace(code=code)


def test_get_effective_permission_codes_merges_role_and_group_permissions():
    user = SimpleNamespace(
        role=SimpleNamespace(permission_groups=[_permission('user.read'), _permission('document.read')]),
        groups=[
            SimpleNamespace(group=SimpleNamespace(permission_groups=[_permission('group.read'), _permission(None)])),
            SimpleNamespace(group=SimpleNamespace(permission_groups=[_permission('user.read')])),
            SimpleNamespace(group=None),
        ],
    )

    assert get_effective_permission_codes(user) == {'user.read', 'document.read', 'group.read'}


def test_get_effective_permission_codes_handles_missing_relationships():
    assert get_effective_permission_codes(SimpleNamespace()) == set()
    assert get_effective_permission_codes(SimpleNamespace(role=None, groups=None)) == set()
