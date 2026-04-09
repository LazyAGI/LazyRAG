import uuid
from sqlalchemy.orm import Session, joinedload
from models import Group, GroupPermission, PermissionGroup, UserGroup


class GroupRepository:

    def __init__(self):
        self.model = Group

    def _get_by_id(self, session: Session, group_id: uuid.UUID) -> Group | None:
        return session.query(self.model).filter_by(id=group_id).first()

    def _get_by_tenant_and_name(self, session: Session, tenant_id: str, group_name: str) -> Group | None:
        return session.query(self.model).filter_by(tenant_id=tenant_id, group_name=group_name).first()

    def _list_paginated(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[Group], int]:
        q = session.query(self.model).order_by(self.model.id)
        count_q = session.query(self.model)
        if search:
            like = f'%{search}%'
            q = q.filter(self.model.group_name.ilike(like))
            count_q = count_q.filter(self.model.group_name.ilike(like))
        if tenant_id is not None:
            q = q.filter(self.model.tenant_id == tenant_id)
            count_q = count_q.filter(self.model.tenant_id == tenant_id)
        total = count_q.count()
        groups = q.offset((page - 1) * page_size).limit(page_size).all()
        return groups, total

    def _create(
        self,
        session: Session,
        tenant_id: str,
        group_name: str,
        remark: str = '',
        creator_user_id: uuid.UUID | None = None,
    ) -> Group:
        g = self.model(
            tenant_id=tenant_id,
            group_name=group_name,
            remark=remark,
            creator_user_id=creator_user_id,
        )
        session.add(g)
        session.commit()
        session.refresh(g)
        return g

    def _delete(self, session: Session, group: Group) -> None:
        session.delete(group)
        session.commit()

    @classmethod
    def get_by_id(cls, session: Session, group_id: uuid.UUID) -> Group | None:
        return cls()._get_by_id(session, group_id)

    @classmethod
    def get_by_tenant_and_name(cls, session: Session, tenant_id: str, group_name: str) -> Group | None:
        return cls()._get_by_tenant_and_name(session, tenant_id, group_name)

    @classmethod
    def list_paginated(
        cls,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[Group], int]:
        return cls()._list_paginated(session, page, page_size, search, tenant_id)

    @classmethod
    def create(
        cls,
        session: Session,
        tenant_id: str,
        group_name: str,
        remark: str = '',
        creator_user_id: uuid.UUID | None = None,
    ) -> Group:
        return cls()._create(
            session, tenant_id, group_name, remark, creator_user_id
        )

    @classmethod
    def delete(cls, session: Session, group: Group) -> None:
        cls()._delete(session, group)


class UserGroupRepository:
    """Repository for UserGroup model. Uses session.query(Model).filter_by(...)."""

    def __init__(self):
        self.model = UserGroup

    def _list_by_group_id(self, session: Session, group_id: uuid.UUID) -> list[UserGroup]:
        return (
            session.query(self.model)
            .options(joinedload(UserGroup.user))
            .filter_by(group_id=group_id)
            .order_by(self.model.id)
            .all()
        )

    def _get_by_group_and_user(
        self,
        session: Session,
        group_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: str | None = None,
    ) -> UserGroup | None:
        q = session.query(self.model).filter_by(group_id=group_id, user_id=user_id)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        return q.first()

    def _get_by_group_and_users(
        self, session: Session, group_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> list[UserGroup]:
        if not user_ids:
            return []
        return (
            session.query(self.model)
            .filter_by(group_id=group_id)
            .filter(self.model.user_id.in_(user_ids))
            .all()
        )

    def _add(
        self,
        session: Session,
        tenant_id: str,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
        role: str = 'member',
        creator_user_id: uuid.UUID | None = None,
    ) -> UserGroup:
        ug = self.model(
            tenant_id=tenant_id,
            user_id=user_id,
            group_id=group_id,
            role=role,
            creator_user_id=creator_user_id,
        )
        session.add(ug)
        session.commit()
        session.refresh(ug)
        return ug

    def _remove_by_group_and_users(
        self,
        session: Session,
        group_id: uuid.UUID,
        user_ids: list[uuid.UUID],
    ) -> None:
        session.query(self.model).filter_by(group_id=group_id).filter(
            self.model.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        session.commit()

    def _set_member_role(self, session: Session, row: UserGroup, role: str) -> None:
        row.role = role
        session.commit()

    @classmethod
    def list_by_group_id(cls, session: Session, group_id: uuid.UUID) -> list[UserGroup]:
        return cls()._list_by_group_id(session, group_id)

    @classmethod
    def get_by_group_and_user(
        cls,
        session: Session,
        group_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: str | None = None,
    ) -> UserGroup | None:
        return cls()._get_by_group_and_user(session, group_id, user_id, tenant_id)

    @classmethod
    def get_by_group_and_users(
        cls, session: Session, group_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> list[UserGroup]:
        return cls()._get_by_group_and_users(session, group_id, user_ids)

    @classmethod
    def add(
        cls,
        session: Session,
        tenant_id: str,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
        role: str = 'member',
        creator_user_id: uuid.UUID | None = None,
    ) -> UserGroup:
        return cls()._add(session, tenant_id, user_id, group_id, role, creator_user_id)

    @classmethod
    def remove_by_group_and_users(
        cls,
        session: Session,
        group_id: uuid.UUID,
        user_ids: list[uuid.UUID],
    ) -> None:
        cls()._remove_by_group_and_users(session, group_id, user_ids)

    @classmethod
    def set_member_role(cls, session: Session, row: UserGroup, role: str) -> None:
        cls()._set_member_role(session, row, role)


class GroupPermissionRepository:
    """Group-to-permission-group mapping.

    Group members automatically have group permissions during authorization
    (union with role permissions).
    """

    @classmethod
    def get_permission_codes(cls, session: Session, group_id: uuid.UUID) -> list[str]:
        """Return permission-group code list bound to a group."""
        rows = (
            session.query(PermissionGroup.code)
            .join(GroupPermission, GroupPermission.permission_group_id == PermissionGroup.id)
            .filter(GroupPermission.group_id == group_id)
            .all()
        )
        return [r[0] for r in rows]

    @classmethod
    def replace_permissions(
        cls, session: Session, group_id: uuid.UUID, permission_group_ids: set[uuid.UUID]
    ) -> None:
        """Fully replace group permission bindings (delete then insert, ensuring no duplicates)."""
        session.query(GroupPermission).filter_by(group_id=group_id).delete(synchronize_session=False)
        for pg_id in permission_group_ids:
            session.add(GroupPermission(group_id=group_id, permission_group_id=pg_id))
        session.commit()
