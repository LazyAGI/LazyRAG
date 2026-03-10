import re
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from passlib.context import CryptContext

from core.errors import AuthError, ErrorCodes, raise_error
from core.rate_limit import login_rate_limiter
from models import User
from repositories import UserRepository


pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._@#-]*[a-zA-Z0-9]$')
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 32

def validate_username(username: str) -> bool:
    """校验用户名格式：至少2位，以字母或数字开头/结尾，中间仅允许字母、数字、. _ @ # -"""
    if not username or len(username) < 2:
        return False
    return USERNAME_PATTERN.match(username) is not None


def validate_password(password: str) -> bool:
    """校验密码强度：8~32位，且同时包含大写、小写、数字、特殊符号各至少一个"""
    if not password or len(password) < PASSWORD_MIN_LEN or len(password) > PASSWORD_MAX_LEN:
        return False
    has_upper = bool(re.search(r'[A-Z]', password))
    has_lower = bool(re.search(r'[a-z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:\'",.<>/?`~]', password))
    return has_upper and has_lower and has_digit and has_special


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def register_user(
    *,
    db: Session,
    username: str,
    password: str,
    role_id: int,
    email: str | None = None,
    tenant_id: str | None = None,
) -> User:
    username = (username or '').strip()
    if not username:
        raise_error(ErrorCodes.USERNAME_REQUIRED, exc_cls=AuthError)
    if not validate_username(username):
        raise_error(
            ErrorCodes.INVALID_USERNAME,
            extra_msg='用户名至少2个字符，以字母或数字开头/结尾，中间仅允许字母、数字、. _ @ # -',
            exc_cls=AuthError,
        )
    if not password:
        raise_error(ErrorCodes.PASSWORD_REQUIRED, exc_cls=AuthError)
    if not validate_password(password):
        raise_error(
            ErrorCodes.INVALID_PASSWORD,
            extra_msg='密码长度8~32位，且同时包含大写、小写、数字、特殊符号各至少一个',
            exc_cls=AuthError,
        )
    try:
        return UserRepository.create(
            db,
            username=username,
            password_hash=hash_password(password),
            role_id=role_id,
            tenant_id=(tenant_id or ''),
            email=email,
            display_name=username,
            disabled=False,
        )
    except IntegrityError:
        db.rollback()
        raise_error(ErrorCodes.USER_ALREADY_EXISTS, exc_cls=AuthError)


def authenticate_user(*, db: Session, username: str, password: str) -> User:
    """认证用户并做登录失败限流(与 LazyCraft 对齐：同一账号 3 次失败/分钟)。"""
    user = UserRepository.get_by_username(db, username)
    if not user:
        raise_error(ErrorCodes.INVALID_CREDENTIALS, exc_cls=AuthError)
    if login_rate_limiter.is_limited(user.id):
        raise_error(ErrorCodes.LOGIN_LOCKED, exc_cls=AuthError)
    if not verify_password(password, user.password_hash):
        login_rate_limiter.record_failure(user.id)
        raise_error(ErrorCodes.INVALID_CREDENTIALS, exc_cls=AuthError)
    if user.disabled:
        raise_error(ErrorCodes.USER_DISABLED, exc_cls=AuthError)
    return user
