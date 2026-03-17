"""鉴权与权限相关接口。

- POST /api/auth/authorize：供网关（如 Kong）做 RBAC 鉴权，根据请求 method+path 与用户权限返回是否放行。
"""
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from jose import JWTError, jwt

from core.errors import ErrorCodes, raise_error
from core.security import jwt_secret
from core.database import SessionLocal
from repositories import UserRepository
from schemas.auth import AuthorizeBody, AuthorizeResponse


router = APIRouter(prefix='/auth', tags=['authorization'])
logger = logging.getLogger('auth-service')

BUILTIN_ADMIN_ROLE = 'system-admin'
API_PERMISSIONS_MAP: dict[tuple[str, str], list[str]] = {}


def _normalize_path(path: str) -> str:
    return path.rstrip('/') or '/'


def _path_matches_pattern(path: str, pattern: str) -> bool:
    path_segs = [s for s in path.split('/') if s]
    pattern_segs = [s for s in pattern.split('/') if s]
    if len(path_segs) != len(pattern_segs):
        return False
    for pseg, mseg in zip(path_segs, pattern_segs):
        if not mseg.startswith('{') or not mseg.endswith('}'):
            if pseg != mseg:
                return False
    return True


def _required_permissions_for(method: str, path: str) -> list[str] | None:
    key = (method, path)
    if key in API_PERMISSIONS_MAP:
        return API_PERMISSIONS_MAP[key]
    for (m, pattern), perms in API_PERMISSIONS_MAP.items():
        if m == method and _path_matches_pattern(path, pattern):
            return perms
    return None


def load_api_permissions() -> None:
    global API_PERMISSIONS_MAP
    path = os.environ.get('LAZYRAG_AUTH_API_PERMISSIONS_FILE')
    path = Path(path) if path else Path(__file__).resolve().parent.parent / 'api_permissions.json'
    if not path.exists():
        logger.warning('api_permissions.json not found at %s; RBAC authorize will allow all', path)
        API_PERMISSIONS_MAP = {}
        return
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        API_PERMISSIONS_MAP = {}
        for item in data:
            method = (item.get('method') or 'GET').upper()
            p = _normalize_path(item.get('path') or '/')
            API_PERMISSIONS_MAP[(method, p)] = list(item.get('permissions') or [])
        logger.info('Loaded %d API permission entries from %s', len(API_PERMISSIONS_MAP), path)
    except Exception as e:
        logger.exception('Failed to load api_permissions from %s: %s', path, e)
        API_PERMISSIONS_MAP = {}


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


@router.post('/authorize', response_model=AuthorizeResponse)
def authorize(body: AuthorizeBody, request: Request):
    """
    鉴权：供网关(Kong)调用，根据请求的 method、path 与用户 Bearer token 判断是否放行
      1. 若接口未配置所需权限则直接放行；
      2. 否则校验用户角色与权限组，管理员或具备任一所需权限则放行；
      3. 否则 403。
    """
    method = (body.method or 'GET').upper()
    path = _normalize_path(body.path or '/')
    required = _required_permissions_for(method, path)
    if not required:
        return {'allowed': True}
    auth_header = request.headers.get('authorization') or ''
    token = auth_header.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token:
        raise_error(ErrorCodes.UNAUTHORIZED)
    user_id = _user_id_from_token(token)
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
    if user.role.name == BUILTIN_ADMIN_ROLE:
        return {'allowed': True}
    from core.permissions import get_effective_permission_codes
    effective = get_effective_permission_codes(user)
    if effective & set(required):
        return {'allowed': True}
    raise_error(ErrorCodes.FORBIDDEN)
