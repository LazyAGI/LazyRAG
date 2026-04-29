# auth-service Unit Tests

Tests for the FastAPI auth service (`JWT`, `RBAC`, users, roles, Alembic).

## Setup

```bash
pip install -r backend/auth-service/requirements.txt
pip install -r tests/backend/auth-service/requirements-test.txt
```

## Run

From project root:

```bash
python -m pytest tests/backend/auth-service/ -v
```

Or from this directory:

```bash
cd ../../.. && python -m pytest tests/backend/auth-service/ -v
```

## Strategy

- **DB**: isolated SQLite test database file configured in `conftest.py`
- **JWT**: Test secret in env
- **Startup**: app startup runs Alembic and bootstrap during integration-style API tests
- **Mocks**: Redis-dependent behavior is stubbed in targeted tests when the goal is unit coverage rather than Redis integration
