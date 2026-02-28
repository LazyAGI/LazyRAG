# Backend service layout

- **common**: Shared package (sibling to core and auth-service) providing `permission_required(...)` for static analysis. Used by both core and auth-service; no per-request auth logic here.
- **auth-service**: Users and auth. Register, login, JWT, `/api/auth/validate`, and **centralized RBAC** via `/api/auth/authorize`. User/role endpoints (list roles, set permissions, etc.) are annotated with `permission_required("user.read")` or `user.write` and are protected by Kong like core.
- **core**: Business API. Exposes `/api/hello`, `/api/admin`, etc. Routes use `permission_required(...)` for **static analysis only**; no per-route auth in FastAPI.

## Centralized authorization (Kong + auth-service)

1. **Static analysis**: When you build auth-service, the image build runs `scripts/extract_api_permissions.py` to scan **both core and auth-service** and write `api_permissions.json` into the image. No manual step needed. The file is gitignored.
2. **auth-service** loads that file and exposes `POST /api/auth/authorize` (body: `method`, `path`; header: `Authorization`). Routes not in the map (e.g. login, register) are allowed without a token; others require a valid JWT and the listed permission(s). Path params (e.g. `/api/auth/roles/{role_id}`) are matched so Kong can authorize concrete paths like `/api/auth/roles/1`.
3. **Kong** uses the `rbac-auth` Lua plugin on **both** the auth route and the core route: before proxying, it calls auth-service `/api/auth/authorize`; on 401/403 it returns that to the client; on 200 it forwards the request.

So neither core nor auth-service performs route-level auth; Kong does it centrally for all protected APIs.

## Admin account (bootstrap)

On first run, auth-service creates a built-in admin user from environment variables:

- **Username**: `BOOTSTRAP_ADMIN_USERNAME` (default in docker-compose: **admin**)
- **Password**: `BOOTSTRAP_ADMIN_PASSWORD` (default in docker-compose: **admin**)

So with the repo’s `docker-compose.yml`, the admin login is **admin / admin**.

If you upgraded from an older version that used `users.role` (string), the app migrates that to `role_id` on startup. If login/register still fail, remove the DB volume and start fresh: `docker compose down -v && docker compose up -d --build`.

## Deploy

1. Build and run: `docker compose up --build`. Building auth-service automatically runs the permission extract script (core + auth-service → api_permissions.json inside the image).

2. Optional: run the script locally to inspect or commit a snapshot: `python3 backend/scripts/extract_api_permissions.py --output path/to/api_permissions.json --exclude scripts,core backend/core backend/auth-service`. The generated file is gitignored.

3. Kong: if you see `module 'resty.http' not found`, build the custom Kong image: in `docker-compose.yml` set `build: ./kong` instead of `image: kong:3.6` and remove the rbac-auth volume mount.

## Standalone deployment

- **auth-service**: Requires DB and env vars like `JWT_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`. Optional: `AUTH_API_PERMISSIONS_FILE` for the API–permission map.
- **core**: No auth env; Kong (or another gateway) calls auth-service for RBAC.

Kong routes `/api/auth` to auth-service and `/api` to core; both routes use the rbac-auth plugin for centralized RBAC.
