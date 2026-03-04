"""
Unit tests for auth_service module (register_user, authenticate_user, hash/verify).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, User
from auth_service import hash_password, verify_password, register_user, authenticate_user, AuthError


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


def test_hash_verify_password():
    h = hash_password('mypass')
    assert h != 'mypass'
    assert verify_password('mypass', h) is True
    assert verify_password('wrong', h) is False


def test_register_user(db_session, role_id):
    user = register_user(db=db_session, username='u1', password='p1', role_id=role_id)
    assert user.id is not None
    assert user.username == 'u1'
    assert user.password_hash != 'p1'


def test_register_duplicate_raises(db_session, role_id):
    register_user(db=db_session, username='dup', password='p', role_id=role_id)
    with pytest.raises(AuthError, match='already exists'):
        register_user(db=db_session, username='dup', password='p2', role_id=role_id)


def test_authenticate_user(db_session, role_id):
    register_user(db=db_session, username='a1', password='secret', role_id=role_id)
    user = authenticate_user(db=db_session, username='a1', password='secret')
    assert user.username == 'a1'


def test_authenticate_wrong_password(db_session, role_id):
    register_user(db=db_session, username='a2', password='secret', role_id=role_id)
    with pytest.raises(AuthError, match='invalid'):
        authenticate_user(db=db_session, username='a2', password='wrong')


def test_authenticate_nonexistent(db_session, role_id):
    with pytest.raises(AuthError, match='invalid'):
        authenticate_user(db=db_session, username='nonexistent', password='x')
