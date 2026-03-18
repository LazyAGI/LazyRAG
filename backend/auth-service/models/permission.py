import uuid

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.types import Uuid as UuidType

from .base import Base


class PermissionGroup(Base):
    __tablename__ = 'permission_groups'

    id = mapped_column(
        UuidType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='Primary key UUID',
    )
    code = mapped_column(String(128), unique=True, nullable=False, index=True, comment='权限码，如 user.read / document.add')
    description = mapped_column(String(255), nullable=False, default='', comment='中文描述，如 查询用户 / 新增文档')
    module = mapped_column(String(64), nullable=False, default='', index=True, comment='模块：document / user / app / qa')
    action = mapped_column(String(16), nullable=False, default='', comment='动作类别：read / write / admin')
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment='创建时间')
    updated_at = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment='更新时间')

    roles = relationship(
        'Role',
        secondary='role_permissions',
        back_populates='permission_groups',
    )
    groups = relationship(
        'Group',
        secondary='group_permissions',
        back_populates='permission_groups',
    )
