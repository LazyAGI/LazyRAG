from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import mapped_column, relationship

from .base import Base


class Role(Base):
    __tablename__ = 'roles'

    id = mapped_column(Integer, primary_key=True, autoincrement=True, comment='主键')
    name = mapped_column(String(64), unique=True, nullable=False, index=True, comment='角色名称')
    built_in = mapped_column(Boolean, nullable=False, default=False, comment='是否内置角色，不可删')

    permission_groups = relationship(
        'PermissionGroup',
        secondary='role_permissions',
        back_populates='roles',
    )


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    __table_args__ = (UniqueConstraint('role_id', 'permission_group_id', name='uq_role_permission'),)

    id = mapped_column(Integer, primary_key=True, autoincrement=True, comment='主键')
    role_id = mapped_column(ForeignKey('roles.id', ondelete='CASCADE'), nullable=False, index=True, comment='角色 id')
    permission_group_id = mapped_column(
        ForeignKey('permission_groups.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='权限组 id',
    )
