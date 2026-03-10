from sqlalchemy.orm import Session, joinedload
from models import Role, RolePermission


class RoleRepository:

    def __init__(self):
        self.model = Role

    def _get_by_name(self, session: Session, name: str) -> Role | None:
        return session.query(self.model).filter_by(name=name).first()

    def _get_by_id(self, session: Session, role_id: int) -> Role | None:
        return session.get(self.model, role_id)

    def _get_with_permission_groups(self, session: Session, role_id: int) -> Role | None:
        return (
            session.query(self.model)
            .options(joinedload(Role.permission_groups))
            .filter_by(id=role_id)
            .first()
        )

    def _get_names_in(self, session: Session, names: list[str]) -> set[str]:
        rows = session.query(self.model.name).filter(self.model.name.in_(names)).all()
        return set(r[0] for r in rows)

    def _count(self, session: Session) -> int:
        return session.query(self.model).count()

    def _list_all_ordered(self, session: Session) -> list[Role]:
        return session.query(self.model).order_by(self.model.name).all()

    def _create(self, session: Session, name: str, built_in: bool = False) -> Role:
        role = self.model(name=name, built_in=built_in)
        session.add(role)
        session.commit()
        session.refresh(role)
        return role

    def _delete(self, session: Session, role: Role) -> None:
        session.delete(role)
        session.commit()

    def _replace_permissions(self, session: Session, role_id: int, permission_group_ids: set[int]) -> None:
        session.query(RolePermission).filter_by(role_id=role_id).delete(synchronize_session=False)
        for pg_id in permission_group_ids:
            session.add(RolePermission(role_id=role_id, permission_group_id=pg_id))
        session.commit()

    @classmethod
    def get_by_name(cls, session: Session, name: str) -> Role | None:
        return cls()._get_by_name(session, name)

    @classmethod
    def get_by_id(cls, session: Session, role_id: int) -> Role | None:
        return cls()._get_by_id(session, role_id)

    @classmethod
    def get_with_permission_groups(cls, session: Session, role_id: int) -> Role | None:
        return cls()._get_with_permission_groups(session, role_id)

    @classmethod
    def get_names_in(cls, session: Session, names: list[str]) -> set[str]:
        return cls()._get_names_in(session, names)

    @classmethod
    def count(cls, session: Session) -> int:
        return cls()._count(session)

    @classmethod
    def list_all_ordered(cls, session: Session) -> list[Role]:
        return cls()._list_all_ordered(session)

    @classmethod
    def create(cls, session: Session, name: str, built_in: bool = False) -> Role:
        return cls()._create(session, name, built_in)

    @classmethod
    def delete(cls, session: Session, role: Role) -> None:
        cls()._delete(session, role)

    @classmethod
    def replace_permissions(cls, session: Session, role_id: int, permission_group_ids: set[int]) -> None:
        cls()._replace_permissions(session, role_id, permission_group_ids)
