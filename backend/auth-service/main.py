from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload, Session

from auth_security import (
    create_access_token,
    hash_refresh_token,
    jwt_secret,
    refresh_token_expires_at,
    generate_refresh_token,
)
from auth_service import AuthError, authenticate_user, register_user
from bootstrap import bootstrap
from db import SessionLocal, engine
from models import Base, PermissionGroup, RefreshToken, Role, RolePermission, User

app = FastAPI(title="Auth Service")
bearer_scheme = HTTPBearer(auto_error=False)

BUILTIN_ADMIN_ROLE = "admin"


class RegisterBody(BaseModel):
    username: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


class RoleCreateBody(BaseModel):
    name: str


class RolePermissionsBody(BaseModel):
    permission_groups: list[str]


class UserRoleBody(BaseModel):
    role_id: int


@app.on_event("startup")
def on_startup():
    import logging
    logger = logging.getLogger("auth-service")
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            bootstrap(db)
        logger.info("Bootstrap completed")
    except Exception as e:
        logger.exception("Bootstrap failed: %s", e)
        raise


def _current_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> int:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = jwt.decode(credentials.credentials, jwt_secret(), algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_admin(user_id: int = Depends(_current_user_id)) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id).options(joinedload(User.role)))
    if not user or user.role.name != BUILTIN_ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin required")
    return user


def _default_role_id(db: Session) -> int:
    role = db.scalar(select(Role).where(Role.name == "user"))
    if not role:
        raise HTTPException(status_code=500, detail="Default role 'user' not found")
    return role.id


@app.get("/api/auth/health")
def api_health():
    from sqlalchemy import func
    with SessionLocal() as db:
        admin_id = db.scalar(select(Role.id).where(Role.name == "admin"))
        user_id = db.scalar(select(Role.id).where(Role.name == "user"))
        n_roles = db.scalar(select(func.count()).select_from(Role))
        n_users = db.scalar(select(func.count()).select_from(User))
    return {
        "status": "ok",
        "roles_count": n_roles,
        "users_count": n_users,
        "bootstrap_ok": bool(admin_id and user_id),
    }


@app.post("/api/auth/register")
def api_register(body: RegisterBody):
    with SessionLocal() as db:
        role_id = _default_role_id(db)
        try:
            user = register_user(db=db, username=body.username, password=body.password, role_id=role_id)
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e))
        role = db.scalar(select(Role).where(Role.id == user.role_id))
        role_name = role.name if role else "user"
    return {"id": user.id, "username": user.username, "role": role_name}


@app.post("/api/auth/login")
def api_login(body: LoginBody):
    with SessionLocal() as db:
        try:
            user = authenticate_user(db=db, username=body.username, password=body.password)
        except AuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        user = db.scalar(select(User).where(User.id == user.id).options(joinedload(User.role)))
        user_id = user.id
        role_name = user.role.name
        access_token = create_access_token(subject=str(user_id), role=role_name)
        refresh_token = generate_refresh_token()
        token_hash = hash_refresh_token(refresh_token)
        expires_at = refresh_token_expires_at()
        db.add(
            RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": role_name,
        "expires_in": 60 * 60,
    }


@app.post("/api/auth/validate")
def api_validate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    """Validate JWT and return sub, role and permissions for downstream services."""
    if not credentials or credentials.credentials is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.id == user_id).options(
                joinedload(User.role).joinedload(Role.permission_groups)
            )
        )
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    permissions = [p.name for p in user.role.permission_groups]
    return {"sub": sub, "role": user.role.name, "permissions": permissions}


@app.post("/api/auth/refresh")
def api_refresh(body: RefreshBody):
    if not body.refresh_token or not body.refresh_token.strip():
        raise HTTPException(status_code=401, detail="refresh_token required")

    token_hash = hash_refresh_token(body.refresh_token.strip())
    now_utc = datetime.now(timezone.utc)

    with SessionLocal() as db:
        row = db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.expires_at > now_utc,
            )
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh_token")

        user = db.scalar(select(User).where(User.id == row.user_id))
        if not user:
            db.delete(row)
            db.commit()
            raise HTTPException(status_code=401, detail="User not found")

        db.delete(row)
        new_refresh_token = generate_refresh_token()
        new_hash = hash_refresh_token(new_refresh_token)
        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=new_hash,
                expires_at=refresh_token_expires_at(),
            )
        )
        db.commit()

    with SessionLocal() as db:
        user_loaded = db.scalar(select(User).where(User.id == user.id).options(joinedload(User.role)))
    role_name = user_loaded.role.name
    access_token = create_access_token(subject=str(user.id), role=role_name)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 60 * 60,
    }


@app.get("/api/auth/permission-groups")
def api_list_permission_groups(_: User = Depends(_require_admin)):
    with SessionLocal() as db:
        groups = db.scalars(select(PermissionGroup).order_by(PermissionGroup.name)).all()
    return [{"id": g.id, "name": g.name} for g in groups]


@app.get("/api/auth/roles")
def api_list_roles(_: User = Depends(_require_admin)):
    with SessionLocal() as db:
        roles = db.scalars(select(Role).order_by(Role.name)).all()
    return [{"id": r.id, "name": r.name, "built_in": r.built_in} for r in roles]


@app.post("/api/auth/roles")
def api_create_role(body: RoleCreateBody, _: User = Depends(_require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    with SessionLocal() as db:
        if db.scalar(select(Role).where(Role.name == name)):
            raise HTTPException(status_code=400, detail="Role name already exists")
        role = Role(name=name, built_in=False)
        db.add(role)
        db.commit()
        db.refresh(role)
    return {"id": role.id, "name": role.name, "built_in": False}


@app.delete("/api/auth/roles/{role_id}")
def api_delete_role(role_id: int, _: User = Depends(_require_admin)):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.id == role_id))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.built_in:
            raise HTTPException(status_code=400, detail="Cannot delete built-in role")
        db.delete(role)
        db.commit()
    return {"ok": True}


@app.get("/api/auth/roles/{role_id}/permissions")
def api_get_role_permissions(role_id: int, _: User = Depends(_require_admin)):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.id == role_id).options(joinedload(Role.permission_groups)))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
    return {"role_id": role_id, "permission_groups": [p.name for p in role.permission_groups]}


@app.put("/api/auth/roles/{role_id}/permissions")
def api_set_role_permissions(role_id: int, body: RolePermissionsBody, _: User = Depends(_require_admin)):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.id == role_id))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.built_in and role.name == BUILTIN_ADMIN_ROLE:
            raise HTTPException(status_code=400, detail="Cannot change admin role permissions")
        pg_ids = set()
        for name in body.permission_groups:
            pg = db.scalar(select(PermissionGroup).where(PermissionGroup.name == name))
            if pg:
                pg_ids.add(pg.id)
        db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for pg_id in pg_ids:
            db.add(RolePermission(role_id=role_id, permission_group_id=pg_id))
        db.commit()
    return {"ok": True}


@app.get("/api/auth/users")
def api_list_users(_: User = Depends(_require_admin)):
    with SessionLocal() as db:
        users = db.scalars(select(User).options(joinedload(User.role)).order_by(User.id)).all()
    return [
        {"id": u.id, "username": u.username, "role_id": u.role_id, "role_name": u.role.name}
        for u in users
    ]


@app.patch("/api/auth/users/{user_id}")
def api_set_user_role(user_id: int, body: UserRoleBody, _: User = Depends(_require_admin)):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id).options(joinedload(User.role)))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.role.name == BUILTIN_ADMIN_ROLE:
            raise HTTPException(status_code=400, detail="Admin account role cannot be changed")
        user.role_id = body.role_id
        db.commit()
    return {"ok": True}
