"""角色与权限组业务逻辑：API 层调用本模块，本模块调用 Repository。"""
import uuid

from core.database import SessionLocal
from core.errors import ErrorCodes, raise_error
from repositories import PermissionGroupRepository, RoleRepository


class RoleService:
    """Role and permission group CRUD."""

    def list_permission_groups(self) -> list[dict]:
        """List all permission groups."""
        with SessionLocal() as db:
            groups = PermissionGroupRepository.list_all_ordered(db)
            return [
                {
                    'id': str(g.id),
                    'code': g.code,
                    'description': g.description,
                    'module': g.module,
                    'action': g.action,
                }
                for g in groups
            ]

    def list_roles(self) -> list[dict]:
        """List all roles."""
        with SessionLocal() as db:
            roles = RoleRepository.list_all_ordered(db)
            return [{'id': str(r.id), 'name': r.name, 'built_in': r.built_in} for r in roles]

    def create_role(self, name: str) -> dict:
        """Create role. Raises if name empty or duplicate. Returns {'id', 'name', 'built_in'}."""
        name = (name or '').strip()
        if not name:
            raise_error(ErrorCodes.ROLE_NAME_REQUIRED)
        with SessionLocal() as db:
            if RoleRepository.get_by_name(db, name):
                raise_error(ErrorCodes.ROLE_NAME_EXISTS)
            role = RoleRepository.create(db, name, built_in=False)
            return {'id': str(role.id), 'name': role.name, 'built_in': False}

    def delete_role(self, role_id: uuid.UUID) -> None:
        """Delete role. Raises if not found or built-in."""
        with SessionLocal() as db:
            role = RoleRepository.get_by_id(db, role_id)
            if not role:
                raise_error(ErrorCodes.ROLE_NOT_FOUND)
            if role.built_in:
                raise_error(ErrorCodes.CANNOT_DELETE_BUILTIN_ROLE)
            RoleRepository.delete(db, role)

    def get_role_permissions(self, role_id: uuid.UUID) -> list[str]:
        """Get permission group codes for a role. Raises if role not found."""
        with SessionLocal() as db:
            role = RoleRepository.get_with_permission_groups(db, role_id)
            if not role:
                raise_error(ErrorCodes.ROLE_NOT_FOUND)
            return [p.code for p in role.permission_groups]

    def set_role_permissions(self, role_id: uuid.UUID, permission_groups: list[str]) -> None:
        """Set role permissions (full replace). Raises if role not found or system-admin."""
        with SessionLocal() as db:
            role = RoleRepository.get_by_id(db, role_id)
            if not role:
                raise_error(ErrorCodes.ROLE_NOT_FOUND)
            if role.built_in and role.name == 'system-admin':
                raise_error(ErrorCodes.CANNOT_CHANGE_ADMIN_PERMS)
            pg_ids = set()
            for code in permission_groups:
                pg = PermissionGroupRepository.get_by_code(db, code)
                if pg:
                    pg_ids.add(pg.id)
            RoleRepository.replace_permissions(db, role_id, pg_ids)


role_service = RoleService()
