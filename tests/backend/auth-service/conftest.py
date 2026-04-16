"""
Pytest fixtures for auth-service tests.
Sets env before any app import so DB uses SQLite in-memory.
"""
import os
import sys

# Must set env before importing app
os.environ['LAZYRAG_DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['LAZYRAG_JWT_SECRET'] = 'test-secret'
os.environ['LAZYRAG_JWT_TTL_MINUTES'] = '60'
os.environ['LAZYRAG_JWT_REFRESH_TTL_DAYS'] = '7'
_test_dir = os.path.dirname(os.path.abspath(__file__))
os.environ['LAZYRAG_AUTH_API_PERMISSIONS_FILE'] = os.path.join(_test_dir, 'api_permissions_test.json')
os.environ['LAZYRAG_AUTH_SERVICE_INTERNAL_TOKEN'] = 'test-internal-token'

# Add auth-service to path (run from project root: pytest tests/backend/auth-service/)
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_auth_svc = os.path.join(_root, 'backend', 'auth-service')
if _auth_svc not in sys.path:
    sys.path.insert(0, _auth_svc)

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)
