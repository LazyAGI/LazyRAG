from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import mapped_column, relationship

from .base import Base


class User(Base):
    __tablename__ = 'users'

    id = mapped_column(Integer, primary_key=True, autoincrement=True, comment='主键，供其他表关联')
    username = mapped_column(String(128), unique=True, index=True, nullable=False, comment='用户名')
    display_name = mapped_column(String(255), nullable=False, default='', comment='用户显示名')
    password_hash = mapped_column(String(255), nullable=False, comment='密码哈希')
    role_id = mapped_column(ForeignKey('roles.id', ondelete='RESTRICT'), nullable=False, index=True, comment='角色 id，外键')

    tenant_id = mapped_column(String(64), nullable=False, default='', index=True, comment='租户 id')
    email = mapped_column(String(255), nullable=True, index=True, comment='邮箱')
    phone = mapped_column(String(64), nullable=False, default='', comment='手机号')
    remark = mapped_column(String(255), nullable=False, default='', comment='备注')
    creator = mapped_column(String(128), nullable=False, default='', comment='创建者')

    created_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment='创建时间',
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment='更新时间',
    )
    last_login_time = mapped_column(DateTime(timezone=True), nullable=True, comment='最后登录时间')
    updated_pwd_time = mapped_column(DateTime(timezone=True), nullable=True, comment='修改密码时间')

    disabled = mapped_column(Boolean, nullable=False, default=False, index=True, comment='是否禁用')
    source = mapped_column(String(32), nullable=False, default='platform', comment='用户来源')

    role = relationship('Role', lazy='raise')
    groups = relationship('UserGroup', back_populates='user', cascade='all, delete-orphan')
