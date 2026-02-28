# Backend service layout

- **auth-service**: Users and auth. Handles register, login, JWT issuance, and `/api/auth/validate` for downstream services to validate tokens and get role/permissions from DB.
- **business**: Business API. Exposes `/api/hello`, `/api/admin`, etc., with `permission_required(...)`; calls auth-service to validate token and check permissions.

## Admin account (bootstrap)

On first run, auth-service creates a built-in admin user from environment variables:

- **Username**: `BOOTSTRAP_ADMIN_USERNAME` (default in docker-compose: **admin**)
- **Password**: `BOOTSTRAP_ADMIN_PASSWORD` (default in docker-compose: **admin**)

So with the repo’s `docker-compose.yml`, the admin login is **admin / admin**.

If you upgraded from an older version that used `users.role` (string), the app migrates that to `role_id` on startup. If login/register still fail, remove the DB volume and start fresh: `docker compose down -v && docker compose up -d --build`.

## Standalone deployment

- **auth-service**: Requires DB and env vars like `JWT_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`; see `backend/auth-service/Dockerfile`.
- **business**: Set `AUTH_SERVICE_URL` to the auth-service URL; see `backend/business/Dockerfile`.

Kong routes `/api/auth` to auth-service and `/api` to business.
