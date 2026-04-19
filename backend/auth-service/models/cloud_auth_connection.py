import uuid

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import mapped_column

from .base import Base


class CloudAuthConnection(Base):
    __tablename__ = 'cloud_auth_connections'

    connection_id = mapped_column(String(64), primary_key=True, default=lambda: f'conn_{uuid.uuid4().hex}')
    tenant_id = mapped_column(String(64), nullable=False, index=True, default='', comment='Tenant id')
    provider = mapped_column(String(64), nullable=False, index=True, comment='Cloud provider name')
    auth_mode = mapped_column(String(32), nullable=False, default='oauth_user', comment='tenant/oauth_user/service_account')
    credential_ciphertext = mapped_column(Text, nullable=False, comment='Encrypted app credential payload')
    auth_state_ciphertext = mapped_column(Text, nullable=False, default='', comment='Encrypted token/auth state')
    status = mapped_column(String(32), nullable=False, default='ACTIVE', index=True, comment='ACTIVE/EXPIRED/ERROR/REVOKED')
    last_error = mapped_column(Text, nullable=False, default='', comment='Last error message')
    created_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment='Created at',
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment='Updated at',
    )
