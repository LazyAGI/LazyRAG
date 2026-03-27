"""Effective user permission calculation: role permissions ∪ group permissions, without duplicate storage, merged dynamically during authorization."""


def get_effective_permission_codes(user) -> set[str]:
    """
    Return effective permission code set = role-bound permission groups ∪ permission groups bound to all joined groups.
    Ensures: group permission changes take effect automatically for members; users inherit group permissions when joining; role permissions are preserved without duplicate data.
    """
    role_codes = set()
    role = getattr(user, 'role', None)
    if role:
        for p in getattr(role, 'permission_groups', None) or []:
            code = getattr(p, 'code', None)
            if code:
                role_codes.add(code)

    group_codes = set()
    for ug in getattr(user, 'groups', None) or []:
        group = getattr(ug, 'group', None)
        if not group:
            continue
        for p in getattr(group, 'permission_groups', None) or []:
            code = getattr(p, 'code', None)
            if code:
                group_codes.add(code)

    return role_codes | group_codes
