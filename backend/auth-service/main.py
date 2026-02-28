import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import delete, select

from auth_security import (
    create_access_token,
    hash_refresh_token,
    jwt_secret,
    refresh_token_expires_at,
    generate_refresh_token,
)
from auth_service import AuthError, authenticate_user, register_user
from db import SessionLocal, engine
from models import Base, RefreshToken, User

app = FastAPI(title="Auth Service")
bearer_scheme = HTTPBearer(auto_error=False)


class RegisterBody(BaseModel):
    username: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


def _bootstrap_admin() -> None:
    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return
    with SessionLocal() as db:
        exists = db.scalar(select(User).where(User.username == username))
        if exists:
            return
        try:
            register_user(db=db, username=username, password=password, role="admin")
        except AuthError:
            return


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _bootstrap_admin()


@app.post("/api/auth/register")
def api_register(body: RegisterBody):
    with SessionLocal() as db:
        try:
            user = register_user(db=db, username=body.username, password=body.password, role="user")
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/api/auth/login")
def api_login(body: LoginBody):
    with SessionLocal() as db:
        try:
            user = authenticate_user(db=db, username=body.username, password=body.password)
        except AuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

        user_id = user.id
        user_role = user.role
        access_token = create_access_token(subject=str(user_id), role=user_role)
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
        "role": user_role,
        "expires_in": 60 * 60,  # access_token lifetime in seconds for client refresh logic
    }


@app.post("/api/auth/validate")
def api_validate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    """Validate JWT and return current user sub and role from DB for business and other downstream services."""
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
    return {"sub": sub, "role": user.role}


@app.post("/api/auth/refresh")
def api_refresh(body: RefreshBody):
    """Exchange refresh_token for a new access_token. Uses rotation: invalidate old refresh_token and issue a new one on success."""
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

        # Rotation: invalidate old refresh_token and issue a new one
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

    access_token = create_access_token(subject=str(user.id), role=user.role)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 60 * 60,
    }
