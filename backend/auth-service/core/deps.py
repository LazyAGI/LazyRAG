import os
import secrets
import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from core.database import SessionLocal
from core.errors import ErrorCodes, raise_error
from core.security import jwt_secret
from models import User
from repositories import UserRepository


bearer_scheme = HTTPBearer(auto_error=False)

_INTERNAL_TOKEN_HEADER = 'X-LazyRAG-Internal-Token'


def require_internal_service_token(request: Request) -> None:
    """Restrict server-to-server routes; core must send matching header."""
    expected = (os.environ.get('LAZYRAG_AUTH_SERVICE_INTERNAL_TOKEN') or '').strip()
    if not expected:
        raise_error(ErrorCodes.FORBIDDEN)
    got = (request.headers.get(_INTERNAL_TOKEN_HEADER) or '').strip()
    exp_b = expected.encode('utf-8')
    got_b = got.encode('utf-8')
    if len(got_b) != len(exp_b) or not secrets.compare_digest(got_b, exp_b):
        raise_error(ErrorCodes.UNAUTHORIZED)


def _user_id_from_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=['HS256'])
    except JWTError:
        raise_error(ErrorCodes.UNAUTHORIZED)

    sub = payload.get('sub')
    if not sub:
        raise_error(ErrorCodes.UNAUTHORIZED)

    try:
        return uuid.UUID(sub)
    except (TypeError, ValueError):
        raise_error(ErrorCodes.UNAUTHORIZED)


def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> uuid.UUID:
    if not credentials or not credentials.credentials:
        raise_error(ErrorCodes.UNAUTHORIZED)
    return _user_id_from_token(credentials.credentials)


def current_user(user_id: uuid.UUID = Depends(current_user_id)) -> User:  # noqa: B008
    with SessionLocal() as db:
        user = UserRepository.get_by_id(
            db,
            user_id,
            load_role=True,
            load_permission_groups=True,
            load_groups=True,
            load_group_permission_groups=True,
        )
    if not user:
        raise_error(ErrorCodes.UNAUTHORIZED)
    if user.disabled:
        raise_error(ErrorCodes.USER_DISABLED)
    return user


def require_admin(user: User = Depends(current_user)) -> User:  # noqa: B008
    if user.role.name != 'system-admin':
        raise_error(ErrorCodes.ADMIN_REQUIRED)
    return user
