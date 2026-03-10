import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base


class UserGroup(Base):
    __tablename__ = 'user_groups'
    __table_args__ = (UniqueConstraint('tenant_id', 'user_id', 'group_id', name='uq_tenant_user_group'),)

    id = mapped_column(Integer, primary_key=True, autoincrement=True, comment='主键')
    tenant_id = mapped_column(String(64), nullable=False, default='', index=True, comment='租户 id')
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True, comment='用户 id')
    group_id = mapped_column(
        UuidType(as_uuid=True),
        ForeignKey('groups.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='用户组 id',
    )
    role = mapped_column(String(16), nullable=False, default='member', comment='组内角色，如 member')
    creator_user_id = mapped_column(Integer, nullable=True, comment='添加该成员的操作人用户 id')

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='创建时间')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='更新时间')

    user = relationship('User', back_populates='groups', lazy='raise')
    group = relationship('Group', back_populates='members', lazy='raise')
