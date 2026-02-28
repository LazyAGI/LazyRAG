# Backend service layout

- **auth-service**: Users and auth. Handles register, login, JWT issuance, and `/api/auth/validate` for downstream services to validate tokens and get role from DB.
- **business**: Business API. Exposes `/api/hello`, `/api/admin`, etc., with `@roles_required(...)`; calls auth-service to validate token and get role.

## Standalone deployment

- **auth-service**: Requires DB and env vars like `JWT_SECRET`; see `backend/auth-service/Dockerfile`.
- **business**: Set `AUTH_SERVICE_URL` to the auth-service URL; see `backend/business/Dockerfile`.

Kong routes `/api/auth` to auth-service and `/api` to business.
