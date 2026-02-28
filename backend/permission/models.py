from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PermissionGroup(Base):
    __tablename__ = "permission_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    built_in: Mapped[bool] = mapped_column(nullable=False, default=False)

    permission_groups: Mapped[list["PermissionGroup"]] = relationship(
        "PermissionGroup",
        secondary="role_permissions",
        back_populates="roles",
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_group_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_group_id: Mapped[int] = mapped_column(
        ForeignKey("permission_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )


PermissionGroup.roles = relationship(
    "Role",
    secondary="role_permissions",
    back_populates="permission_groups",
)
