"""
Unit tests for auth_service module (register_user, authenticate_user, hash/verify).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.errors import AuthError
from models import Base
from services.auth_service import auth_service, login_rate_limiter


@pytest.fixture
def db_session():
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def role_id(db_session):
    from models import Role
    r = Role(name='user', built_in=True)
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r.id


@pytest.fixture(autouse=True)
def disable_login_rate_limit(monkeypatch):
    monkeypatch.setattr(login_rate_limiter, 'is_limited', lambda user_id: False)
    monkeypatch.setattr(login_rate_limiter, 'record_failure', lambda user_id: None)


def test_hash_verify_password():
    h = auth_service.hash_password('Strong1!')
    assert h != 'mypass'
    assert auth_service.verify_password('Strong1!', h) is True
    assert auth_service.verify_password('wrong', h) is False


def test_register_user(db_session, role_id):
    user = auth_service.register_user(db=db_session, username='u1', password='Strong1!', role_id=role_id)
    assert user.id is not None
    assert user.username == 'u1'
    assert user.password_hash != 'Strong1!'


def test_register_duplicate_raises(db_session, role_id):
    auth_service.register_user(db=db_session, username='dup', password='Strong1!', role_id=role_id)
    with pytest.raises(AuthError, match='already exists'):
        auth_service.register_user(db=db_session, username='dup', password='Strong2!', role_id=role_id)


def test_authenticate_user(db_session, role_id):
    auth_service.register_user(db=db_session, username='a1', password='Strong1!', role_id=role_id)
    user = auth_service.authenticate_user(db=db_session, username='a1', password='Strong1!')
    assert user.username == 'a1'


def test_authenticate_wrong_password(db_session, role_id):
    auth_service.register_user(db=db_session, username='a2', password='Strong1!', role_id=role_id)
    with pytest.raises(AuthError, match='Invalid username or password'):
        auth_service.authenticate_user(db=db_session, username='a2', password='Wrong1!!')


def test_authenticate_nonexistent(db_session, role_id):
    with pytest.raises(AuthError, match='Invalid username or password'):
        auth_service.authenticate_user(db=db_session, username='nonexistent', password='Strong1!')
