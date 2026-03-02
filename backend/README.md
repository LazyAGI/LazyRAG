# Backend service layout

- **auth-service** (Python/FastAPI): Users and auth. Register, login, JWT, `/api/auth/validate`, and **centralized RBAC** via `/api/auth/authorize`. Routes are annotated with `@permission_required("user.read")` or `user.write`; the extract script reads these and Kong enforces them.
- **core** (Go): Business API. Exposes `/hello`, `/admin`, `/api/hello`, `/api/admin`. Permissions are declared at registration via **handleAPI(mux, method, path, []string{"perm"}, handler)**; the extract script parses these calls. No per-route auth in Go; Kong does it.

## Centralized authorization (Kong + auth-service)

1. **Static analysis**: When you build auth-service, the image build runs `scripts/extract_api_permissions.py` to scan **core** (Go) and **auth-service** (Python) and write `api_permissions.json` into the image. The script supports:
   - **Python**: `@permission_required("perm1", "perm2")` on FastAPI routes (`app.get("/path", ...)` etc.).
   - **Go**: Calls to **handleAPI(mux, method, path, []string{"perm"}, handler)** at route registration. Example: `handleAPI(mux, "GET", "/api/hello", []string{"user.read"}, func(...))`
2. **auth-service** loads that file and exposes `POST /api/auth/authorize`. Routes not in the map are allowed without a token; others require a valid JWT and the listed permission(s).
3. **Kong** uses the `rbac-auth` plugin on both auth and core routes: it calls auth-service `/api/auth/authorize`; on 200 it forwards the request.

So neither core nor auth-service performs route-level auth; Kong does it centrally for all protected APIs.

## Admin account (bootstrap)

On first run, auth-service creates a built-in admin user from environment variables:

- **Username**: `BOOTSTRAP_ADMIN_USERNAME` (default in docker-compose: **admin**)
- **Password**: `BOOTSTRAP_ADMIN_PASSWORD` (default in docker-compose: **admin**)

So with the repo’s `docker-compose.yml`, the admin login is **admin / admin**.

If you upgraded from an older version that used `users.role` (string), the app migrates that to `role_id` on startup. If login/register still fail, remove the DB volume and start fresh: `docker compose down -v && docker compose up -d --build`.

## Deploy

1. Build and run: `docker compose up --build`. Building auth-service runs the permission extract script (core Go + auth-service Python → api_permissions.json inside the image).

2. Optional: run the script locally: `python3 backend/scripts/extract_api_permissions.py --output backend/auth-service/api_permissions.json --exclude scripts,core,vendor backend/core backend/auth-service`. The generated file is gitignored.

3. Kong: if you see `module 'resty.http' not found`, build the custom Kong image: in `docker-compose.yml` set `build: ./kong` instead of `image: kong:3.6` and remove the rbac-auth volume mount.

## Standalone deployment

- **auth-service**: Requires DB and env vars like `JWT_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`. Optional: `AUTH_API_PERMISSIONS_FILE` for the API–permission map.
- **core**: No auth env; Kong (or another gateway) calls auth-service for RBAC.

Kong routes `/api/auth` to auth-service and `/api` to core; both use the rbac-auth plugin for centralized RBAC.
