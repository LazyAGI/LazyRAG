from sqlalchemy.orm import Session

from models import CloudAuthConnection


class CloudAuthConnectionRepository:
    @classmethod
    def get_by_id(cls, session: Session, connection_id: str) -> CloudAuthConnection | None:
        return (
            session.query(CloudAuthConnection)
            .filter(CloudAuthConnection.connection_id == (connection_id or '').strip())
            .first()
        )

    @classmethod
    def create(
        cls,
        session: Session,
        *,
        connection_id: str,
        tenant_id: str,
        provider: str,
        auth_mode: str,
        credential_ciphertext: str,
        auth_state_ciphertext: str,
        status: str = 'ACTIVE',
        last_error: str = '',
    ) -> CloudAuthConnection:
        row = CloudAuthConnection(
            connection_id=(connection_id or '').strip(),
            tenant_id=(tenant_id or '').strip(),
            provider=(provider or '').strip().lower(),
            auth_mode=(auth_mode or '').strip().lower(),
            credential_ciphertext=credential_ciphertext,
            auth_state_ciphertext=auth_state_ciphertext,
            status=(status or '').strip().upper() or 'ACTIVE',
            last_error=last_error or '',
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    @classmethod
    def save(cls, session: Session, row: CloudAuthConnection) -> CloudAuthConnection:
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
