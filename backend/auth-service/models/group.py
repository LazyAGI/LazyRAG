import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base
from .user_group import UserGroup


class GroupPermission(Base):
    """用户组与权限组的关联表：组内成员自动拥有该组绑定的权限（与角色权限取并集，不重复存储）。"""
    __tablename__ = 'group_permissions'
    __table_args__ = (UniqueConstraint('group_id', 'permission_group_id', name='uq_group_permission'),)

    id = mapped_column(
        UuidType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='Primary key UUID',
    )
    group_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('groups.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='Group id',
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


class Group(Base):
    __tablename__ = 'groups'
    __table_args__ = (UniqueConstraint('tenant_id', 'group_name', name='uq_tenant_group_name'),)

    id = mapped_column(UuidType(as_uuid=True), primary_key=True, default=uuid.uuid4, comment='Primary key UUID')
    tenant_id = mapped_column(String(64), nullable=False, default='', index=True, comment='Tenant id')
    group_name = mapped_column(String(255), nullable=False, index=True, comment='Group name')
    remark = mapped_column(String(255), nullable=False, default='', comment='Remark')
    creator_user_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment='Creator user id',
    )

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='Created at')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='Updated at')

    members = relationship('UserGroup', back_populates='group', cascade='all, delete-orphan')
    permission_groups = relationship(
        'PermissionGroup',
        secondary='group_permissions',
        back_populates='groups',
    )
