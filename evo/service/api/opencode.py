from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from evo.runtime.config import EvoConfig
from evo.service import opencode_admin
class OpencodeProviderUpdate(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    base_url: str | None = None
    label: str | None = None
class OpencodeSelect(BaseModel):
    provider: str = Field(min_length=1)
    model: str | None = None
def build_opencode_router(cfg: EvoConfig) -> APIRouter:
    router = APIRouter(prefix='/v1/evo/opencode', tags=['opencode'])
    @router.get('/config')
    def read_config() -> dict[str, Any]:
        return opencode_admin.read_status(cfg)
    @router.put('/config')
    def write_config(req: OpencodeProviderUpdate) -> dict[str, Any]:
        try:
            return opencode_admin.write_config(cfg, provider=req.provider, model=req.model, api_key=req.api_key, base_url=req.base_url, label=req.label)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    @router.post('/select')
    def select_config(req: OpencodeSelect) -> dict[str, Any]:
        try:
            return opencode_admin.select_config(cfg, provider=req.provider, model=req.model)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    return router
