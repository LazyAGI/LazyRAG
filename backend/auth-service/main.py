import json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.auth import router as auth_router
from api.authorization import router as authorization_router
from api.group import router as group_router
from api.role import router as role_router
from api.user import router as user_router
from core.errors import AppException, error_payload_from_exception


app = FastAPI(
    title='Auth Service',
    description='LazyRAG 认证与授权服务（登录、注册、Token、用户/角色/组管理）',
    version='1.0.0',
    docs_url='/docs',
    redoc_url=None,
    oauth2_redirect_url=None,
    openapi_url='/openapi.json',
)

# 文档与 OpenAPI 路径不经过响应包装中间件
_SWAGGER_PATHS = {'/openapi.json', '/docs'}


def _copy_headers(headers) -> dict[str, str]:
    d = dict(headers)
    d.pop('content-length', None)
    return d


@app.middleware('http')
async def _standardize_json_response(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in _SWAGGER_PATHS:
        return response

    content_type = (response.headers.get('content-type') or '').lower()
    if 'application/json' not in content_type:
        return response

    body = b''
    async for chunk in response.body_iterator:
        body += chunk

    try:
        payload = json.loads(body.decode('utf-8')) if body else None
    except Exception:
        return Response(
            content=body,
            status_code=response.status_code,
            headers=_copy_headers(response.headers),
            media_type='application/json',
        )

    if isinstance(payload, dict) and (('swagger' in payload or 'openapi' in payload) and 'info' in payload and 'paths' in payload):
        return Response(
            content=body,
            status_code=response.status_code,
            headers=_copy_headers(response.headers),
            media_type='application/json',
        )

    if isinstance(payload, dict) and 'code' in payload and 'message' in payload and 'data' in payload:
        payload['code'] = response.status_code
        return JSONResponse(content=payload, status_code=response.status_code, headers=_copy_headers(response.headers))

    if 200 <= response.status_code < 300:
        wrapped = {'code': response.status_code, 'message': 'success', 'data': payload}
    else:
        msg = None
        if isinstance(payload, dict):
            msg = payload.get('message')
        if not isinstance(msg, str) or not msg:
            msg = 'An error occurred'
        wrapped = {'code': response.status_code, 'message': msg, 'data': payload}

    return JSONResponse(content=wrapped, status_code=response.status_code, headers=_copy_headers(response.headers))


@app.exception_handler(AppException)
def _handle_app_exception(_, exc: AppException):
    return JSONResponse(status_code=exc.http_code, content=error_payload_from_exception(exc))


@app.exception_handler(StarletteHTTPException)
def _handle_http_exception(_, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "message": message, "data": None})


@app.exception_handler(RequestValidationError)
def _handle_validation_error(_, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"code": 400, "message": "参数错误", "data": exc.errors()})


app.include_router(auth_router)
app.include_router(authorization_router)
app.include_router(user_router)
app.include_router(role_router)
app.include_router(group_router)
