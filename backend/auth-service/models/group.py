import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base
from .user_group import UserGroup


class Group(Base):
    __tablename__ = 'groups'
    __table_args__ = (UniqueConstraint('tenant_id', 'group_name', name='uq_tenant_group_name'),)

    id = mapped_column(UuidType(as_uuid=True), primary_key=True, default=uuid.uuid4, comment='主键 UUID')
    tenant_id = mapped_column(String(64), nullable=False, default='', index=True, comment='租户 id')
    group_name = mapped_column(String(255), nullable=False, index=True, comment='用户组名称')
    remark = mapped_column(String(255), nullable=False, default='', comment='备注')
    creator_user_id = mapped_column(Integer, nullable=True, comment='创建人用户 id')

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='创建时间')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='更新时间')

    members = relationship('UserGroup', back_populates='group', cascade='all, delete-orphan')
