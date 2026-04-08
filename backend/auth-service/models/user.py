import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base
from .user_group import UserGroup


class User(Base):
    __tablename__ = 'users'

    id = mapped_column(
        UuidType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='Primary key UUID',
    )
    username = mapped_column(String(128), unique=True, index=True, nullable=False, comment='Username')
    display_name = mapped_column(String(255), nullable=False, default='', comment='Display name')
    password_hash = mapped_column(String(255), nullable=False, comment='Password hash')
    role_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('roles.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
        comment='Role id, FK',
    )
    tenant_id = mapped_column(String(64), nullable=False, default='', index=True, comment='Tenant ID')
    email = mapped_column(String(255), nullable=True, index=True, comment='Email')
    phone = mapped_column(String(64), nullable=False, default='', comment='Phone number')
    remark = mapped_column(String(255), nullable=False, default='', comment='Remark')
    creator = mapped_column(String(128), nullable=False, default='', comment='Creator')
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
    last_login_time = mapped_column(DateTime(timezone=True), nullable=True, comment='Last login time')
    updated_pwd_time = mapped_column(DateTime(timezone=True), nullable=True, comment='Password updated at')
    disabled = mapped_column(Boolean, nullable=False, default=False, index=True, comment='Disabled')
    source = mapped_column(String(32), nullable=False, default='platform', comment='User source')

    role = relationship('Role', lazy='raise')
    groups = relationship(
        'UserGroup',
        back_populates='user',
        foreign_keys=[UserGroup.user_id],
        cascade='all, delete-orphan',
    )
