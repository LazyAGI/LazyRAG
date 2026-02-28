from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select

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
from models import Base, RefreshToken, User

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


class UserRoleBody(BaseModel):
    role_name: str


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
        user = db.scalar(select(User).where(User.id == user_id))
    if not user or user.role_name != BUILTIN_ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin required")
    return user


@app.get("/api/auth/health")
def api_health():
    from sqlalchemy import func
    with SessionLocal() as db:
        n_users = db.scalar(select(func.count()).select_from(User))
        admin_user = db.scalar(select(User).where(User.role_name == BUILTIN_ADMIN_ROLE))
    return {
        "status": "ok",
        "users_count": n_users,
        "bootstrap_ok": admin_user is not None,
    }


@app.post("/api/auth/register")
def api_register(body: RegisterBody):
    with SessionLocal() as db:
        try:
            user = register_user(db=db, username=body.username, password=body.password, role_name="user")
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"id": user.id, "username": user.username, "role": user.role_name}


@app.post("/api/auth/login")
def api_login(body: LoginBody):
    with SessionLocal() as db:
        try:
            user = authenticate_user(db=db, username=body.username, password=body.password)
        except AuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        user_id = user.id
        role_name = user.role_name
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
    """Validate JWT and return sub and role (identity only; permissions from permission service)."""
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
        user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"sub": sub, "role": user.role_name}


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

    role_name = user.role_name
    access_token = create_access_token(subject=str(user.id), role=role_name)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 60 * 60,
    }


@app.get("/api/auth/users")
def api_list_users(_: User = Depends(_require_admin)):
    with SessionLocal() as db:
        users = db.scalars(select(User).order_by(User.id)).all()
    return [
        {"id": u.id, "username": u.username, "role_name": u.role_name}
        for u in users
    ]


@app.patch("/api/auth/users/{user_id}")
def api_set_user_role(user_id: int, body: UserRoleBody, _: User = Depends(_require_admin)):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.role_name == BUILTIN_ADMIN_ROLE:
            raise HTTPException(status_code=400, detail="Admin account role cannot be changed")
        user.role_name = body.role_name.strip()
        db.commit()
    return {"ok": True}
