"""Permission service: permission groups, roles, role-permission mapping. Admin APIs require auth via auth-service."""
import os

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from bootstrap import bootstrap
from db import SessionLocal, engine
from models import Base, PermissionGroup, Role, RolePermission

app = FastAPI(title="Permission Service")
bearer_scheme = HTTPBearer(auto_error=False)

BUILTIN_ADMIN_ROLE = "admin"


class RoleCreateBody(BaseModel):
    name: str


class RolePermissionsBody(BaseModel):
    permission_groups: list[str]


def _auth_service_url() -> str:
    url = os.environ.get("AUTH_SERVICE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("AUTH_SERVICE_URL is required for admin endpoints")
    return url


async def _require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{_auth_service_url()}/api/auth/validate",
                headers={"Authorization": f"Bearer {credentials.credentials}"},
            )
    except Exception:
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = r.json()
    role = data.get("role")
    if role != BUILTIN_ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin required")


@app.on_event("startup")
def on_startup():
    import logging
    logger = logging.getLogger("permission")
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            bootstrap(db)
        logger.info("Bootstrap completed")
    except Exception as e:
        logger.exception("Bootstrap failed: %s", e)
        raise


@app.get("/api/permission/permission-groups")
def api_list_permission_groups(_: None = Depends(_require_admin)):
    with SessionLocal() as db:
        groups = db.scalars(select(PermissionGroup).order_by(PermissionGroup.name)).all()
    return [{"id": g.id, "name": g.name} for g in groups]


@app.get("/api/permission/roles")
def api_list_roles(_: None = Depends(_require_admin)):
    with SessionLocal() as db:
        roles = db.scalars(select(Role).order_by(Role.name)).all()
    return [{"id": r.id, "name": r.name, "built_in": r.built_in} for r in roles]


@app.post("/api/permission/roles")
def api_create_role(body: RoleCreateBody, _: None = Depends(_require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    with SessionLocal() as db:
        if db.scalar(select(Role).where(Role.name == name)):
            raise HTTPException(status_code=400, detail="Role name already exists")
        role = Role(name=name, built_in=False)
        db.add(role)
        db.commit()
        db.refresh(role)
    return {"id": role.id, "name": role.name, "built_in": False}


@app.delete("/api/permission/roles/{role_id}")
def api_delete_role(role_id: int, _: None = Depends(_require_admin)):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.id == role_id))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.built_in:
            raise HTTPException(status_code=400, detail="Cannot delete built-in role")
        db.delete(role)
        db.commit()
    return {"ok": True}


@app.get("/api/permission/roles/{role_id}/permissions")
def api_get_role_permissions(role_id: int, _: None = Depends(_require_admin)):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.id == role_id).options(joinedload(Role.permission_groups)))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
    return {"role_id": role_id, "permission_groups": [p.name for p in role.permission_groups]}


@app.put("/api/permission/roles/{role_id}/permissions")
def api_set_role_permissions(role_id: int, body: RolePermissionsBody, _: None = Depends(_require_admin)):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.id == role_id))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.built_in and role.name == BUILTIN_ADMIN_ROLE:
            raise HTTPException(status_code=400, detail="Cannot change admin role permissions")
        pg_ids = set()
        for name in body.permission_groups:
            pg = db.scalar(select(PermissionGroup).where(PermissionGroup.name == name))
            if pg:
                pg_ids.add(pg.id)
        db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for pg_id in pg_ids:
            db.add(RolePermission(role_id=role_id, permission_group_id=pg_id))
        db.commit()
    return {"ok": True}


@app.get("/api/permission/roles/by-name/{role_name}/permissions")
def api_get_permissions_by_role_name(role_name: str):
    """Return list of permission names for the role. Used by core for authorization (no auth)."""
    with SessionLocal() as db:
        role = db.scalar(
            select(Role).where(Role.name == role_name).options(joinedload(Role.permission_groups))
        )
        if not role:
            return {"permissions": []}
    return {"permissions": [p.name for p in role.permission_groups]}
