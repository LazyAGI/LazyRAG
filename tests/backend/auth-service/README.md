# auth-service Unit Tests

Tests for FastAPI auth service (JWT, RBAC, users, roles).

## Setup

```bash
pip install -r ../../../backend/auth-service/requirements.txt
pip install -r requirements-test.txt
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

- **DB**: SQLite in-memory via `LAZYRAG_DATABASE_URL=sqlite:///:memory:` (set in conftest before import)
- **JWT**: Test secret in env
- **No mocks**: Real DB, real JWT; bootstrap runs on startup
