import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base


class UserGroup(Base):
    __tablename__ = 'user_groups'
    __table_args__ = (UniqueConstraint('tenant_id', 'user_id', 'group_id', name='uq_tenant_user_group'),)

    id = mapped_column(
        UuidType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='Primary key UUID',
    )
    tenant_id = mapped_column(String(64), nullable=False, default='', index=True, comment='Tenant id')
    user_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='User id',
    )
    group_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('groups.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='Group id',
    )
    role = mapped_column(String(16), nullable=False, default='member', comment='Role in group, e.g. member')
    creator_user_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment='Creator user id who added this member',
    )

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='Created at')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='Updated at')

    user = relationship('User', back_populates='groups', foreign_keys=[user_id], lazy='raise')
    group = relationship('Group', back_populates='members', lazy='raise')
