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

    result = get_effective_permission_codes(user)

    assert isinstance(result, set)
    assert result == {'user.read', 'document.read', 'group.read'}


def test_get_effective_permission_codes_handles_missing_relationships():
    result_1 = get_effective_permission_codes(SimpleNamespace())
    result_2 = get_effective_permission_codes(SimpleNamespace(role=None, groups=None))

    assert isinstance(result_1, set)
    assert isinstance(result_2, set)
    assert result_1 == set()
    assert result_2 == set()
