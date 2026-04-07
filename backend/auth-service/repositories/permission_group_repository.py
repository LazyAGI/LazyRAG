from sqlalchemy.orm import Session
from models import PermissionGroup


class PermissionGroupRepository:

    def __init__(self):
        self.model = PermissionGroup

    def _get_by_code(self, session: Session, code: str) -> PermissionGroup | None:
        return session.query(self.model).filter_by(code=code).first()

    def _list_all_ordered(self, session: Session) -> list[PermissionGroup]:
        return session.query(self.model).order_by(self.model.module, self.model.code).all()

    def _create(
        self,
        session: Session,
        code: str,
        description: str = '',
        module: str = '',
        action: str = '',
    ) -> PermissionGroup:
        pg = self.model(
            code=code,
            description=description,
            module=module,
            action=action,
        )
        session.add(pg)
        session.commit()
        session.refresh(pg)
        return pg

    @classmethod
    def get_by_code(cls, session: Session, code: str) -> PermissionGroup | None:
        return cls()._get_by_code(session, code)

    @classmethod
    def list_all_ordered(cls, session: Session) -> list[PermissionGroup]:
        return cls()._list_all_ordered(session)

    @classmethod
    def create(
        cls,
        session: Session,
        code: str,
        description: str = '',
        module: str = '',
        action: str = '',
    ) -> PermissionGroup:
        return cls()._create(session, code, description, module, action)
