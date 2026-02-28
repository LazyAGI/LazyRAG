from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from passlib.context import CryptContext

from models import User


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def register_user(*, db: Session, username: str, password: str, role_name: str = "user") -> User:
    user = User(username=username, password_hash=hash_password(password), role_name=role_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AuthError("username already exists")
    db.refresh(user)
    return user


def authenticate_user(*, db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("invalid username or password")
    return user
