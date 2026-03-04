"""
Unit tests for auth-service API endpoints.
Uses SQLite in-memory DB (via conftest env) - no external deps.
"""
import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient):
    r = client.get('/api/auth/health')
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'ok'
    assert 'roles_count' in data
    assert 'users_count' in data
    assert data['bootstrap_ok'] is True


def test_register(client: TestClient):
    r = client.post('/api/auth/register', json={'username': 'testuser', 'password': 'pass123'})
    assert r.status_code == 200
    data = r.json()
    assert data['username'] == 'testuser'
    assert 'id' in data
    assert data['role'] == 'user'


def test_register_duplicate(client: TestClient):
    client.post('/api/auth/register', json={'username': 'dup', 'password': 'p'})
    r = client.post('/api/auth/register', json={'username': 'dup', 'password': 'p'})
    assert r.status_code == 400
    assert 'already exists' in r.json().get('detail', '').lower()


def test_login(client: TestClient):
    client.post('/api/auth/register', json={'username': 'logintest', 'password': 'secret'})
    r = client.post('/api/auth/login', json={'username': 'logintest', 'password': 'secret'})
    assert r.status_code == 200
    data = r.json()
    assert 'access_token' in data
    assert 'refresh_token' in data
    assert data['role'] == 'user'
    assert data['expires_in'] > 0


def test_login_invalid(client: TestClient):
    r = client.post('/api/auth/login', json={'username': 'nonexistent', 'password': 'wrong'})
    assert r.status_code == 401


def test_validate_no_token(client: TestClient):
    r = client.post('/api/auth/validate')
    assert r.status_code == 401


def test_validate_with_token(client: TestClient):
    reg = client.post('/api/auth/register', json={'username': 'valuser', 'password': 'p'})
    assert reg.status_code == 200
    user_id = reg.json()['id']
    login = client.post('/api/auth/login', json={'username': 'valuser', 'password': 'p'})
    token = login.json()['access_token']
    r = client.post('/api/auth/validate', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.json()
    assert data['sub'] == str(user_id)
    assert 'role' in data
    assert 'permissions' in data


def test_refresh(client: TestClient):
    client.post('/api/auth/register', json={'username': 'refuser', 'password': 'p'})
    login = client.post('/api/auth/login', json={'username': 'refuser', 'password': 'p'})
    refresh = login.json()['refresh_token']
    r = client.post('/api/auth/refresh', json={'refresh_token': refresh})
    assert r.status_code == 200
    data = r.json()
    assert 'access_token' in data
    assert 'refresh_token' in data
    assert data['refresh_token'] != refresh  # new token


def test_refresh_invalid(client: TestClient):
    r = client.post('/api/auth/refresh', json={'refresh_token': 'invalid-token'})
    assert r.status_code == 401


def test_authorize_no_required_permission(client: TestClient):
    """When API_PERMISSIONS_MAP has no entry, allow all."""
    r = client.post('/api/auth/authorize', json={'method': 'GET', 'path': '/unknown'})
    assert r.status_code == 200
    assert r.json()['allowed'] is True


def test_authorize_with_token(client: TestClient):
    """With valid token and user.read permission for /api/hello, authorize returns allowed."""
    client.post('/api/auth/register', json={'username': 'authuser', 'password': 'p'})
    login = client.post('/api/auth/login', json={'username': 'authuser', 'password': 'p'})
    token = login.json()['access_token']
    r = client.post(
        '/api/auth/authorize',
        json={'method': 'GET', 'path': '/api/hello'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 200
    assert r.json()['allowed'] is True
