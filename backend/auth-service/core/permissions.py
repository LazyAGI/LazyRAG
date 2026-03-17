"""用户有效权限计算：角色权限 ∪ 所属组的权限，不重复存储，鉴权时动态合并。"""


def get_effective_permission_codes(user) -> set[str]:
    """
    返回用户有效权限码集合 = 角色绑定的权限组 ∪ 所属各组绑定的权限组。
    满足：组增删权限时组内用户自动生效；用户加入组时自动继承组权限；保留原角色权限且无重复数据。
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
