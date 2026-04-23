from __future__ import annotations

from fastapi import FastAPI

from chat.app.api.internal_routes import router

app = FastAPI(title='chat internal-only', version='evo-poc-1')
app.include_router(router)


@app.get('/healthz')
def healthz() -> dict:
    return {'ok': True}
