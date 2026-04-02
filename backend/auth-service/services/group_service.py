"""Group business logic: called by API layer, and this module calls repositories."""
import uuid

from core.database import SessionLocal
from core.errors import ErrorCodes, raise_error
from repositories import (
    GroupPermissionRepository,
    GroupRepository,
    PermissionGroupRepository,
    UserGroupRepository,
    UserRepository,
)


class GroupService:
    """User group CRUD and membership."""

    def list_groups(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated group list. Returns (items, total)."""
        with SessionLocal() as db:
            groups, total = GroupRepository.list_paginated(db, page, page_size, search, tenant_id)
            items = [
                {
                    'group_id': str(g.id),
                    'group_name': g.group_name,
                    'remark': g.remark,
                    'tenant_id': g.tenant_id,
                }
                for g in groups
            ]
            return items, int(total)

    def create_group(
        self,
        group_name: str,
        tenant_id: str,
        remark: str = '',
        creator_user_id: uuid.UUID | None = None,
    ) -> str:
        """Create group. Returns group_id (UUID string)."""
        with SessionLocal() as db:
            g = GroupRepository.create(
                db,
                tenant_id=tenant_id,
                group_name=group_name,
                remark=remark,
                creator_user_id=creator_user_id,
            )
            return str(g.id)

    def get_group(self, group_id: uuid.UUID) -> dict | None:
        """Get group by id. Returns None if not found."""
        with SessionLocal() as db:
            g = GroupRepository.get_by_id(db, group_id)
            if not g:
                return None
            return {
                'group_id': str(g.id),
                'group_name': g.group_name,
                'remark': g.remark,
                'tenant_id': g.tenant_id,
            }

    def update_group(
        self,
        group_id: uuid.UUID,
        group_name: str | None = None,
        remark: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Update group. Raises if not found or validation fails."""
        with SessionLocal() as db:
            g = GroupRepository.get_by_id(db, group_id)
            if not g:
                raise_error(ErrorCodes.GROUP_NOT_FOUND)
            if group_name is not None:
                name = group_name.strip()
                if not name:
                    raise_error(ErrorCodes.GROUP_NAME_EMPTY)
                g.group_name = name
            if remark is not None:
                g.remark = remark
            if tenant_id is not None:
                g.tenant_id = tenant_id
            db.commit()

    def delete_group(self, group_id: uuid.UUID) -> None:
        """Delete group. Raises if not found."""
        with SessionLocal() as db:
            g = GroupRepository.get_by_id(db, group_id)
            if not g:
                raise_error(ErrorCodes.GROUP_NOT_FOUND)
            GroupRepository.delete(db, g)

    def list_group_users(self, group_id: uuid.UUID) -> list[dict]:
        """List members in a group."""
        with SessionLocal() as db:
            rows = UserGroupRepository.list_by_group_id(db, group_id)
            return [
                {
                    'username': r.user.username,
                    'role': r.role,
                    'tenant_id': r.tenant_id,
                }
                for r in rows
            ]

    def add_group_users(
        self,
        group_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        role: str = 'member',
        operator_id: uuid.UUID | None = None,
    ) -> None:
        """Add users to group. Raises if group or any user not found."""
        with SessionLocal() as db:
            group = GroupRepository.get_by_id(db, group_id)
            if not group:
                raise_error(ErrorCodes.GROUP_NOT_FOUND)
            for uid in user_ids:
                user = UserRepository.get_by_id(db, uid)
                if not user:
                    raise_error(ErrorCodes.USER_NOT_FOUND, extra_msg=str(uid))
                exists = UserGroupRepository.get_by_group_and_user(db, group_id, uid, group.tenant_id)
                if exists:
                    continue
                UserGroupRepository.add(
                    db,
                    tenant_id=group.tenant_id,
                    user_id=uid,
                    group_id=group_id,
                    role=role,
                    creator_user_id=operator_id,
                )

    def remove_group_users(self, group_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
        """Remove users from group."""
        with SessionLocal() as db:
            UserGroupRepository.remove_by_group_and_users(db, group_id, user_ids)

    def set_member_role(self, group_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
        """Set member role in group. Raises if membership not found or role empty."""
        if not (role or '').strip():
            raise_error(ErrorCodes.ROLE_REQUIRED)
        with SessionLocal() as db:
            row = UserGroupRepository.get_by_group_and_user(db, group_id, user_id)
            if not row:
                raise_error(ErrorCodes.MEMBERSHIP_NOT_FOUND)
            UserGroupRepository.set_member_role(db, row, role.strip())

    def set_member_roles_batch(
        self, group_id: uuid.UUID, user_ids: list[uuid.UUID], role: str
    ) -> None:
        """Batch update member roles in a group.

        user_ids can contain one or multiple values; raise an error if any
        member is not in the group.
        """
        if not (role or '').strip():
            raise_error(ErrorCodes.ROLE_REQUIRED)
        if not user_ids:
            return
        with SessionLocal() as db:
            rows = UserGroupRepository.get_by_group_and_users(db, group_id, user_ids)
            found_ids = {r.user_id for r in rows}
            missing = [uid for uid in user_ids if uid not in found_ids]
            if missing:
                raise_error(
                    ErrorCodes.MEMBERSHIP_NOT_FOUND,
                    extra_msg=','.join(str(u) for u in missing),
                )
            for row in rows:
                UserGroupRepository.set_member_role(db, row, role.strip())

    def get_group_permissions(self, group_id: uuid.UUID) -> list[str]:
        """Return permission-group code list bound to the group.

        Group members automatically have these permissions during
        authorization (union with role permissions).
        """
        with SessionLocal() as db:
            g = GroupRepository.get_by_id(db, group_id)
            if not g:
                raise_error(ErrorCodes.GROUP_NOT_FOUND)
            return GroupPermissionRepository.get_permission_codes(db, group_id)

    def set_group_permissions(self, group_id: uuid.UUID, permission_groups: list[str]) -> None:
        """Fully replace group permission groups (delete then insert).

        No duplicates are kept. Members automatically get new permissions
        without writing user records separately.
        """
        with SessionLocal() as db:
            g = GroupRepository.get_by_id(db, group_id)
            if not g:
                raise_error(ErrorCodes.GROUP_NOT_FOUND)
            pg_ids = set()
            for code in (permission_groups or []):
                pg = PermissionGroupRepository.get_by_code(db, (code or '').strip())
                if pg:
                    pg_ids.add(pg.id)
            GroupPermissionRepository.replace_permissions(db, group_id, pg_ids)


group_service = GroupService()
