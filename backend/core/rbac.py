"""Permission-based access: validate token with auth-service, load permissions from permission service."""
from __future__ import annotations

import os
from typing import Any, Callable

import httpx
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

BUILTIN_ADMIN_ROLE = "admin"


def permission_required(*permissions: str):
    """Require at least one of the given permission groups (e.g. user.read, document.write)."""
    perm_set = set(permissions)

    def decorator(fn: Callable[..., Any]):
        setattr(fn, "__required_permissions__", perm_set)
        return fn

    return decorator


def _auth_service_url() -> str:
    url = os.environ.get("AUTH_SERVICE_URL")
    if not url:
        raise RuntimeError("AUTH_SERVICE_URL is required")
    return url.rstrip("/")


def _permission_service_url() -> str:
    url = os.environ.get("PERMISSION_SERVICE_URL")
    if not url:
        raise RuntimeError("PERMISSION_SERVICE_URL is required")
    return url.rstrip("/")


async def _validate_token_and_get_permissions(authorization: str) -> dict[str, Any] | None:
    """Validate JWT with auth-service (sub, role), then load permissions from permission service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{_auth_service_url()}/api/auth/validate",
                headers={"Authorization": authorization},
            )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    sub = data.get("sub")
    role = data.get("role")
    if sub is None or role is None:
        return None

    if role == BUILTIN_ADMIN_ROLE:
        return {"sub": sub, "role": role, "permissions": None}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r2 = await client.get(
                f"{_permission_service_url()}/api/permission/roles/by-name/{role}/permissions",
            )
    except Exception:
        return None
    if r2.status_code != 200:
        return {"sub": sub, "role": role, "permissions": []}
    payload = r2.json()
    permissions = list(payload.get("permissions") or [])
    return {"sub": sub, "role": role, "permissions": permissions}


def _has_permission(user: dict, required: set[str]) -> bool:
    if user.get("role") == BUILTIN_ADMIN_ROLE:
        return True
    user_perms = set(user.get("permissions") or [])
    return bool(required & user_perms)


class PermissionProtectedRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Response]:
        original_route_handler = super().get_route_handler()
        required_permissions: set[str] | None = getattr(
            self.endpoint, "__required_permissions__", None
        )

        async def custom_route_handler(request: Request) -> Response:
            if required_permissions:
                auth_header = request.headers.get("authorization", "")
                if not auth_header:
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                user = await _validate_token_and_get_permissions(auth_header)
                if not user:
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                if not _has_permission(user, required_permissions):
                    return JSONResponse({"detail": "Forbidden"}, status_code=403)
                request.state.user = user

            return await original_route_handler(request)

        return custom_route_handler
