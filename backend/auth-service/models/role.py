import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base


class Role(Base):
    __tablename__ = 'roles'

    id = mapped_column(
        UuidType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='Primary key UUID',
    )
    name = mapped_column(String(64), unique=True, nullable=False, index=True, comment='Role name')
    built_in = mapped_column(Boolean, nullable=False, default=False, comment='Built-in role, not deletable')
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='Created at')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='Updated at')

    permission_groups = relationship(
        'PermissionGroup',
        secondary='role_permissions',
        back_populates='roles',
    )


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    __table_args__ = (UniqueConstraint('role_id', 'permission_group_id', name='uq_role_permission'),)

    id = mapped_column(
        UuidType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='Primary key UUID',
    )
    role_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('roles.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='Role id',
    )
    permission_group_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('permission_groups.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='Permission group id',
    )
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='Created at')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='Updated at')
