## Database migrations (Alembic)

This service previously relied on `Base.metadata.create_all()` at startup, which **does not handle schema changes**.

### Setup

Install deps from `requirements.txt`, then run Alembic from this directory (`backend/auth-service`).

### Create initial migration (first time only)

```bash
alembic -c alembic.ini revision --autogenerate -m "init"
alembic -c alembic.ini upgrade head
```

### After changing models

```bash
alembic -c alembic.ini revision --autogenerate -m "schema change"
alembic -c alembic.ini upgrade head
```

### Notes

- DB URL is taken from `LAZYRAG_DATABASE_URL` (same as runtime).
- Migrations are additive: they will **not** delete existing permission codes (that behavior is owned by application logic, not migrations).

