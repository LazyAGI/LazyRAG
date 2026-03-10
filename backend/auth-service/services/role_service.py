"""角色与权限组业务逻辑：API 层调用本模块，本模块调用 Repository。"""
from core.database import SessionLocal
from core.errors import ErrorCodes, raise_error
from repositories import PermissionGroupRepository, RoleRepository


def list_permission_groups() -> list[dict]:
    """查询所有权限组列表。"""
    with SessionLocal() as db:
        groups = PermissionGroupRepository.list_all_ordered(db)
        return [
            {'id': g.id, 'code': g.code, 'description': g.description, 'module': g.module, 'action': g.action}
            for g in groups
        ]


def list_roles() -> list[dict]:
    """查询所有角色列表。"""
    with SessionLocal() as db:
        roles = RoleRepository.list_all_ordered(db)
        return [{'id': r.id, 'name': r.name, 'built_in': r.built_in} for r in roles]


def create_role(name: str) -> dict:
    """创建角色。名称空或重复抛错。返回 {'id', 'name', 'built_in'}。"""
    name = (name or '').strip()
    if not name:
        raise_error(ErrorCodes.ROLE_NAME_REQUIRED)
    with SessionLocal() as db:
        if RoleRepository.get_by_name(db, name):
            raise_error(ErrorCodes.ROLE_NAME_EXISTS)
        role = RoleRepository.create(db, name, built_in=False)
        return {'id': role.id, 'name': role.name, 'built_in': False}


def delete_role(role_id: int) -> None:
    """删除角色。不存在或内置角色抛错。"""
    with SessionLocal() as db:
        role = RoleRepository.get_by_id(db, role_id)
        if not role:
            raise_error(ErrorCodes.ROLE_NOT_FOUND)
        if role.built_in:
            raise_error(ErrorCodes.CANNOT_DELETE_BUILTIN_ROLE)
        RoleRepository.delete(db, role)


def get_role_permissions(role_id: int) -> list[str]:
    """查询角色已绑定的权限组 code 列表。角色不存在返回空列表（或由调用方先校验）。"""
    with SessionLocal() as db:
        role = RoleRepository.get_with_permission_groups(db, role_id)
        if not role:
            raise_error(ErrorCodes.ROLE_NOT_FOUND)
        return [p.code for p in role.permission_groups]


def set_role_permissions(role_id: int, permission_groups: list[str]) -> None:
    """设置角色权限组（全量覆盖）。角色不存在或为 admin 不可改抛错。"""
    with SessionLocal() as db:
        role = RoleRepository.get_by_id(db, role_id)
        if not role:
            raise_error(ErrorCodes.ROLE_NOT_FOUND)
        if role.built_in and role.name == 'admin':
            raise_error(ErrorCodes.CANNOT_CHANGE_ADMIN_PERMS)
        pg_ids = set()
        for code in permission_groups:
            pg = PermissionGroupRepository.get_by_code(db, code)
            if pg:
                pg_ids.add(pg.id)
        RoleRepository.replace_permissions(db, role_id, pg_ids)
