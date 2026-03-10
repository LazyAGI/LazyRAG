import logging

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from core.errors import ErrorCodes, raise_error
from core.security import jwt_secret
from core.database import SessionLocal
from models import User
from repositories import UserRepository


logger = logging.getLogger('auth-service')
bearer_scheme = HTTPBearer(auto_error=False)


def _user_id_from_token(token: str) -> int:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=['HS256'])
    except JWTError:
        raise_error(ErrorCodes.UNAUTHORIZED)
    sub = payload.get('sub')
    if not sub:
        raise_error(ErrorCodes.UNAUTHORIZED)
    try:
        return int(sub)
    except (TypeError, ValueError):
        raise_error(ErrorCodes.UNAUTHORIZED)


def current_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> int:  # noqa: B008
    if not credentials or not credentials.credentials:
        raise_error(ErrorCodes.UNAUTHORIZED)
    return _user_id_from_token(credentials.credentials)


def current_user(user_id: int = Depends(current_user_id)) -> User:  # noqa: B008
    with SessionLocal() as db:
        user = UserRepository.get_by_id(db, user_id, load_role=True, load_permission_groups=True)
    if not user:
        raise_error(ErrorCodes.UNAUTHORIZED)
    return user


def require_admin(user: User = Depends(current_user)) -> User:  # noqa: B008
    if user.role.name != 'admin':
        raise_error(ErrorCodes.ADMIN_REQUIRED)
    return user

