from __future__ import annotations

import os
from typing import Any, Callable

import httpx
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def roles_required(*roles: str):
    role_set = set(roles)

    def decorator(fn: Callable[..., Any]):
        setattr(fn, "__required_roles__", role_set)
        return fn

    return decorator


def _auth_service_url() -> str:
    url = os.environ.get("AUTH_SERVICE_URL")
    if not url:
        raise RuntimeError("AUTH_SERVICE_URL is required")
    return url.rstrip("/")


async def _validate_token_and_get_role(authorization: str) -> dict[str, str] | None:
    """Call auth-service to validate JWT and return sub and role from DB."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{_auth_service_url()}/api/auth/validate",
                headers={"Authorization": authorization},
            )
        if r.status_code != 200:
            return None
        data = r.json()
        sub = data.get("sub")
        role = data.get("role")
        if sub is None or role is None:
            return None
        return {"sub": sub, "role": role}
    except Exception:
        return None


class RoleProtectedRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Response]:
        original_route_handler = super().get_route_handler()
        required_roles: set[str] | None = getattr(self.endpoint, "__required_roles__", None)

        async def custom_route_handler(request: Request) -> Response:
            if required_roles:
                auth_header = request.headers.get("authorization", "")
                if not auth_header:
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                user = await _validate_token_and_get_role(auth_header)
                if not user:
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                if user["role"] not in required_roles:
                    return JSONResponse({"detail": "Forbidden"}, status_code=403)
                request.state.user = user

            return await original_route_handler(request)

        return custom_route_handler
