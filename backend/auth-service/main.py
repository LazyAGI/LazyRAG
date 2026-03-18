import json
import logging
import time
import traceback

import redis
import yaml
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from api.auth import router as auth_router
from api.authorization import router as authorization_router
from api.group import router as group_router
from api.role import router as role_router
from api.user import router as user_router
from core.errors import AppException, ErrorCodes, error_payload_from_exception


logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)

app = FastAPI(
    title='Auth Service',
    description='LazyRAG 认证与授权服务（登录、注册、Token、用户/角色/组管理）',
    version='1.0.0',
    docs_url='/docs',
    redoc_url=None,
    oauth2_redirect_url=None,
    openapi_url='/openapi.json',
)

_SWAGGER_PATHS = {'/openapi.json', '/openapi.yaml', '/docs'}

_logger = logging.getLogger('uvicorn.error')
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _logger.addHandler(logging.StreamHandler())
_logger.propagate = True


@app.middleware('http')
async def _log_request(request: Request, call_next):
    if request.url.path in _SWAGGER_PATHS:
        return await call_next(request)

    client_ip = request.client.host if request.client else None
    _logger.info('Request started: %s %s from %s', request.method, request.url.path, client_ip)
    print(f'Request started: {request.method} {request.url.path} from {client_ip}', flush=True)

    start = time.time()
    try:
        response = await call_next(request)
    except (AppException, redis.exceptions.RedisError, StarletteHTTPException):
        raise
    except Exception as exc:
        cost_ms = int((time.time() - start) * 1000)
        _logger.exception(
            'unhandled_exception method=%s path=%s cost_ms=%d',
            request.method,
            request.url.path,
            cost_ms,
            extra={'method': request.method, 'path': request.url.path, 'cost_ms': cost_ms},
        )
        print(traceback.format_exc(), flush=True)
        _logger.error(
            'unhandled_exception_detail type=%s module=%s message=%s',
            type(exc).__name__,
            type(exc).__module__,
            str(exc),
        )
        print(
            f'unhandled_exception method={request.method} '
            f'path={request.url.path} '
            f'cost_ms={cost_ms} '
            f'type={type(exc).__name__} '
            f'module={type(exc).__module__} '
            f'message={exc}',
            flush=True,
        )
        return JSONResponse(
            status_code=500,
            content={'code': 500, 'message': 'Internal Server Error', 'data': None},
        )

    cost_ms = int((time.time() - start) * 1000)
    extra = {
        'method': request.method,
        'path': request.url.path,
        'status': response.status_code,
        'cost_ms': cost_ms,
    }
    if response.status_code >= 500:
        _logger.error(
            'access-log method=%s path=%s status=%s cost_ms=%d',
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
            extra=extra,
        )
    else:
        _logger.info(
            'access-log method=%s path=%s status=%s cost_ms=%d',
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
            extra=extra,
        )

    print(
        f'access-log method={request.method} '
        f'path={request.url.path} '
        f'status={response.status_code} '
        f'cost_ms={cost_ms}',
        flush=True,
    )
    return response


def _copy_headers(headers) -> dict[str, str]:
    result = dict(headers)
    result.pop('content-length', None)
    return result


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

    if (
        isinstance(payload, dict)
        and ('swagger' in payload or 'openapi' in payload)
        and 'info' in payload
        and 'paths' in payload
    ):
        return Response(
            content=body,
            status_code=response.status_code,
            headers=_copy_headers(response.headers),
            media_type='application/json',
        )

    if isinstance(payload, dict) and {'code', 'message', 'data'} <= payload.keys():
        payload['code'] = response.status_code
        return JSONResponse(
            content=payload,
            status_code=response.status_code,
            headers=_copy_headers(response.headers),
        )

    if 200 <= response.status_code < 300:
        wrapped = {'code': response.status_code, 'message': 'success', 'data': payload}
    else:
        msg = payload.get('message') if isinstance(payload, dict) else None
        if not isinstance(msg, str) or not msg:
            msg = 'An error occurred'
        wrapped = {'code': response.status_code, 'message': msg, 'data': payload}

    return JSONResponse(
        content=wrapped,
        status_code=response.status_code,
        headers=_copy_headers(response.headers),
    )


@app.exception_handler(AppException)
def _handle_app_exception(_, exc: AppException):
    return JSONResponse(
        status_code=exc.http_code,
        content=error_payload_from_exception(exc),
    )


@app.exception_handler(redis.exceptions.RedisError)
def _handle_redis_error(_, exc: redis.exceptions.RedisError):
    tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    _logger.error('redis_error type=%s message=%s\n%s', type(exc).__name__, str(exc), tb)
    print(f'redis_error type={type(exc).__name__} message={exc}\n{tb}', flush=True)

    error = ErrorCodes.REDIS_AUTH_FAILED
    if not isinstance(exc, redis.exceptions.AuthenticationError):
        error = ErrorCodes.REDIS_UNAVAILABLE

    try:
        from core.errors import raise_error

        raise_error(error)
    except AppException as app_exc:
        return JSONResponse(
            status_code=app_exc.http_code,
            content=error_payload_from_exception(app_exc),
        )


@app.exception_handler(StarletteHTTPException)
def _handle_http_exception(_, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else 'HTTP error'
    return JSONResponse(
        status_code=exc.status_code,
        content={'code': exc.status_code, 'message': message, 'data': None},
    )


@app.exception_handler(RequestValidationError)
def _handle_validation_error(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={'code': 400, 'message': '参数错误', 'data': exc.errors()},
    )


@app.get('/openapi.yaml', include_in_schema=False)
def openapi_yaml():
    schema = app.openapi()
    body = yaml.dump(schema, allow_unicode=True, sort_keys=False)
    return Response(content=body, media_type='application/x-yaml')


_API_PREFIX = '/api/authservice'


app.include_router(auth_router, prefix=_API_PREFIX)
app.include_router(authorization_router, prefix=_API_PREFIX)
app.include_router(user_router, prefix=_API_PREFIX)
app.include_router(role_router, prefix=_API_PREFIX)
app.include_router(group_router, prefix=_API_PREFIX)
