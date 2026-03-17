import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import APIRouter, Depends

from api.authorization import load_api_permissions
from bootstrap import bootstrap
from core.deps import bearer_scheme, current_user, require_admin, _user_id_from_token
from core.errors import ErrorCodes, raise_error
from core.refresh_token_store import delete_refresh_token, get_user_id_by_token, set_refresh_token
from core.security import (
    create_access_token,
    generate_jti,
    generate_refresh_token,
    hash_refresh_token,
    jwt_secret,
    jwt_ttl_seconds,
)
from core.database import SessionLocal
from models import User
from repositories import RoleRepository, UserRepository
from schemas.auth import (
    ChangePasswordBody,
    HealthResponse,
    LoginBody,
    LoginResponse,
    LogoutBody,
    MeResponse,
    RefreshBody,
    RegisterBody,
    RegisterResponse,
    SuccessResponse,
    ValidateResponse,
)
from services.auth_service import auth_service


router = APIRouter(prefix='/auth', tags=['auth'])
# 复用 uvicorn 的 logger，确保容器日志可见
logger = logging.getLogger('uvicorn.error')


def _default_role_id(session):
    role = RoleRepository.get_by_name(session, 'user')
    if not role:
        raise_error(ErrorCodes.DEFAULT_ROLE_NOT_FOUND)
    return role.id  # UUID


def _run_alembic_upgrade() -> None:
    """
    执行alembic upgrade head
    """
    auth_service_root = Path(__file__).resolve().parent.parent
    alembic_ini = auth_service_root / 'alembic.ini'
    if not alembic_ini.exists():
        logger.warning('alembic.ini not found at %s; skipping migrations', alembic_ini)
        return
    config = Config(str(alembic_ini))
    config.set_main_option('script_location', str(auth_service_root / 'alembic'))

    try:
        command.upgrade(config, 'head')
        logger.info('Alembic upgrade head completed')
        return
    except Exception as e:
        logger.exception('Alembic upgrade failed: %s', e)
        raise


@router.on_event('startup')
def on_startup():
    """应用启动时：执行迁移、bootstrap 初始化、加载 API 权限配置。"""
    _run_alembic_upgrade()
    with SessionLocal() as db:
        bootstrap(db)
    load_api_permissions()


@router.get('/health', response_model=HealthResponse)
def health():
    """系统健康检查接口，用于监控服务存活状态"""
    return {"status": "ok", "timestamp": time.time()}


@router.post('/register', response_model=RegisterResponse)
def register(body: RegisterBody):
    """用户注册：校验用户名、密码格式及确认密码一致后创建账号，默认角色为 user。"""
    username = (body.username or '').strip()
    password = (body.password or '').strip() if body.password else ''
    confirm = (body.confirm_password or '').strip() if body.confirm_password else ''
    if password != confirm:
        raise_error(ErrorCodes.PASSWORD_CONFIRM_MISMATCH)
    
    with SessionLocal() as db:
        role_id = _default_role_id(db)
        user = auth_service.register_user(
            db=db,
            username=username,
            password=password,
            role_id=role_id,
            email=body.email,
            tenant_id=body.tenant_id,
        )
        role = RoleRepository.get_by_id(db, user.role_id)
        role_name = role.name if role else 'user'
    return {'success': True, 'user_id': str(user.id), 'tenant_id': user.tenant_id, 'role': role_name}


@router.post('/login', response_model=LoginResponse)
def login(body: LoginBody):
    """用户登录：校验用户名密码并通过登录失败限流后，颁发 access_token 与 refresh_token。"""
    username = (body.username or '').strip()
    password = body.password or ''

    logger.info("[auth-service] login enter username=%r", username)
    if not username:
        raise_error(ErrorCodes.USERNAME_REQUIRED)
    if not password:
        raise_error(ErrorCodes.PASSWORD_REQUIRED)
    
    try:
        with SessionLocal() as db:
            user = auth_service.authenticate_user(db=db, username=username, password=password)
            user = UserRepository.get_by_id(db, user.id, load_role=True)
            if not user:
                raise_error(ErrorCodes.UNAUTHORIZED)
            user_id, role_name = user.id, user.role.name
            access_token = create_access_token(
                subject=str(user_id),
                role=role_name,
                tenant_id=(user.tenant_id or None),
                username=user.username,
                jti=generate_jti(),
            )
            refresh_token = generate_refresh_token()
            set_refresh_token(hash_refresh_token(refresh_token), user_id)
    except Exception as e:
        logger.exception("[auth-service] login exception username=%r: %s", username, e)
        raise
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'bearer',
        'role': role_name,
        'expires_in': jwt_ttl_seconds(),
        'tenant_id': user.tenant_id,
    }


@router.post('/refresh', response_model=LoginResponse)
def refresh(body: RefreshBody):
    """刷新 Token：用有效的 refresh_token 换取新的 access_token 与 refresh_token，旧 refresh_token 随即失效。"""
    if not body.refresh_token or not body.refresh_token.strip():
        raise_error(ErrorCodes.REFRESH_TOKEN_REQUIRED)
    token_hash = hash_refresh_token(body.refresh_token.strip())
    user_id = get_user_id_by_token(token_hash)
    if user_id is None:
        raise_error(ErrorCodes.REFRESH_TOKEN_INVALID)
    delete_refresh_token(token_hash)
    with SessionLocal() as db:
        user = UserRepository.get_by_id(db, user_id, load_role=True)
        if not user:
            raise_error(ErrorCodes.UNAUTHORIZED)
        role_name = user.role.name
        tenant_id = user.tenant_id
    new_refresh_token = generate_refresh_token()
    set_refresh_token(hash_refresh_token(new_refresh_token), user_id)
    return {
        'access_token': create_access_token(
            subject=str(user.id),
            role=role_name,
            tenant_id=(tenant_id or None),
            username=user.username,
            jti=generate_jti(),
        ),
        'refresh_token': new_refresh_token,
        'token_type': 'bearer',
        'expires_in': jwt_ttl_seconds(),
        'role': role_name,
        'tenant_id': tenant_id,
    }


# TODO sjh 确认这个方法是不是用于配合kong做鉴权的
@router.post('/validate', response_model=ValidateResponse)
def validate(credentials=Depends(bearer_scheme)):
    """校验 Token：验证请求头中的 Bearer token 是否有效，并返回用户 id、角色、租户及权限列表，供网关或前端做鉴权。"""
    if not credentials or credentials.credentials is None:
        raise_error(ErrorCodes.UNAUTHORIZED)
    user_id = _user_id_from_token(credentials.credentials)
    with SessionLocal() as db:
        user = UserRepository.get_by_id(
            db, user_id,
            load_role=True, load_permission_groups=True,
            load_groups=True, load_group_permission_groups=True,
        )
    if not user:
        raise_error(ErrorCodes.UNAUTHORIZED)
    from core.permissions import get_effective_permission_codes
    return {
        'sub': str(user.id),
        'role': user.role.name,
        'tenant_id': user.tenant_id,
        'permissions': list(get_effective_permission_codes(user)),
    }


@router.get('/me', response_model=MeResponse)
def me(user: User = Depends(current_user)):
    """当前用户信息：根据 Bearer token 返回当前登录用户的 id、用户名、邮箱、状态、角色及有效权限列表（角色权限 ∪ 组权限）。"""
    from core.permissions import get_effective_permission_codes
    return {
        'user_id': str(user.id),
        'username': user.username,
        'display_name': user.display_name or user.username,
        'email': user.email,
        'status': 'inactive' if user.disabled else 'active',
        'role': user.role.name,
        'permissions': list(get_effective_permission_codes(user)),
        'tenant_id': user.tenant_id,
    }


@router.post('/change_password', response_model=SuccessResponse)
def change_password(body: ChangePasswordBody, user: User = Depends(current_user)):
    """修改密码：校验旧密码后，将当前用户密码更新为新密码（新密码需符合强度要求）。"""
    if not auth_service.verify_password(body.old_password, user.password_hash):
        raise_error(ErrorCodes.OLD_PASSWORD_INVALID)
    new_password = (body.new_password or '').strip()
    if not new_password:
        raise_error(ErrorCodes.NEW_PASSWORD_REQUIRED)
    if not auth_service.validate_password(new_password):
        raise_error(ErrorCodes.INVALID_PASSWORD)
    with SessionLocal() as db:
        row = UserRepository.get_by_id(db, user.id)
        if not row:
            raise_error(ErrorCodes.USER_NOT_FOUND)
        row.password_hash = auth_service.hash_password(new_password)
        row.updated_pwd_time = datetime.now(timezone.utc)
        db.commit()
    return {'success': True}


@router.post('/logout', response_model=SuccessResponse)
def logout(body: LogoutBody, user: User = Depends(current_user)):
    """登出：若请求体携带 refresh_token，则服务端使该 refresh_token 失效，前端应清除本地 token。"""
    if not body.refresh_token:
        return {'success': True}
    token_hash = hash_refresh_token(body.refresh_token.strip())
    delete_refresh_token(token_hash)
    return {'success': True}
