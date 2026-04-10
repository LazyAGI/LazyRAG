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
        current_user_id: uuid.UUID | None = None,
        is_system_admin: bool = False,
    ) -> tuple[list[dict], int]:
        """Paginated group list. Returns (items, total).

        - system-admin: returns all groups with optional filters
        - non-admin: returns only groups that current user belongs to
        """
        with SessionLocal() as db:
            if is_system_admin:
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

            if current_user_id is None:
                return [], 0

            user = UserRepository.get_by_id(db, current_user_id, load_groups=True)
            if not user:
                raise_error(ErrorCodes.USER_NOT_FOUND)

            groups = []
            for membership in user.groups:
                group = membership.group
                if not group:
                    continue
                groups.append(
                    {
                        'group_id': str(group.id),
                        'group_name': group.group_name,
                        'remark': group.remark,
                        'tenant_id': group.tenant_id,
                    }
                )

            if tenant_id is not None:
                groups = [g for g in groups if (g.get('tenant_id') or '') == tenant_id]
            if search:
                keyword = search.lower()
                groups = [g for g in groups if keyword in (g.get('group_name') or '').lower()]

            groups.sort(key=lambda item: ((item.get('group_name') or '').lower(), item['group_id']))
            total = len(groups)
            start = (max(page, 1) - 1) * page_size
            end = start + page_size
            return groups[start:end], total

    def create_group(
        self,
        group_name: str,
        tenant_id: str,
        remark: str = '',
        creator_user_id: uuid.UUID | None = None,
    ) -> str:
        """Create group. Returns group_id (UUID string)."""
        name = (group_name or '').strip()
        if not name:
            raise_error(ErrorCodes.GROUP_NAME_REQUIRED)
        with SessionLocal() as db:
            if GroupRepository.get_by_tenant_and_name(db, tenant_id or '', name):
                raise_error(ErrorCodes.GROUP_NAME_EXISTS)
            g = GroupRepository.create(
                db,
                tenant_id=tenant_id or '',
                group_name=name,
                remark=remark or '',
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
                existing = GroupRepository.get_by_tenant_and_name(db, g.tenant_id or '', name)
                if existing and existing.id != g.id:
                    raise_error(ErrorCodes.GROUP_NAME_EXISTS)
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
                    'user_id': str(r.user_id),
                    'username': r.user.username,
                    'role': r.role,
                    'tenant_id': r.tenant_id,
                }
                for r in rows
            ]

    def list_user_groups(self, user_id: uuid.UUID) -> list[dict]:
        """List groups that the specified user belongs to."""
        with SessionLocal() as db:
            user = UserRepository.get_by_id(db, user_id, load_groups=True)
            if not user:
                raise_error(ErrorCodes.USER_NOT_FOUND)
            items = []
            for membership in user.groups:
                group = membership.group
                if not group:
                    continue
                items.append(
                    {
                        'user_id': str(user.id),
                        'group_id': str(group.id),
                        'group_name': group.group_name,
                        'tenant_id': group.tenant_id,
                    }
                )
            return items

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
