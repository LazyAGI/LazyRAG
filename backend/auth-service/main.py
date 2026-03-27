import json
import logging
import time
from pathlib import Path

import redis
import traceback
import yaml
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


# 确保日志可见（uvicorn 的 log_config 可能把默认级别设为 WARNING/且禁用既有 logger）
logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)

_API_PREFIX = '/api/authservice'
_OPENAPI_JSON_PATH = f'{_API_PREFIX}/openapi.json'
_SWAGGER_JSON_PATH = f'{_API_PREFIX}/swagger.json'
_OPENAPI_YAML_PATH = f'{_API_PREFIX}/openapi.yaml'
_DOCS_PATH = f'{_API_PREFIX}/docs'

app = FastAPI(
    title='Auth Service',
    description='LazyRAG 认证与授权服务（登录、注册、Token、用户/角色/组管理）',
    version='1.0.0',
    docs_url=_DOCS_PATH,
    redoc_url=None,
    oauth2_redirect_url=None,
    openapi_url=_OPENAPI_JSON_PATH,
)

_SWAGGER_PATHS = {_OPENAPI_JSON_PATH, _SWAGGER_JSON_PATH, _OPENAPI_YAML_PATH, _DOCS_PATH}

_logger = logging.getLogger('uvicorn.error')
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _logger.addHandler(logging.StreamHandler())
_logger.propagate = True


@app.middleware('http')
async def _log_request(request: Request, call_next):
    """每个请求打印一条相关请求日志 + access-log"""
    if request.url.path in _SWAGGER_PATHS:
        return await call_next(request)
    client_ip = None
    if request.client:
        client_ip = request.client.host
    _logger.info('Request started: %s %s from %s', request.method, request.url.path, client_ip)
    print(f'Request started: {request.method} {request.url.path} from {client_ip}', flush=True)
    start = time.time()
    try:
        response = await call_next(request)
    except AppException:
        # 业务异常交给 exception_handler 统一格式化，不应全部是 500
        raise
    except redis.exceptions.RedisError:
        # 交给 Redis 专用 handler 输出更清晰的错误信息
        raise
    except StarletteHTTPException:
        raise
    except Exception as e:
        cost_ms = int((time.time() - start) * 1000)
        _logger.exception(
            'unhandled_exception method=%s path=%s cost_ms=%d',
            request.method,
            request.url.path,
            cost_ms,
            extra={'method': request.method, 'path': request.url.path, 'cost_ms': cost_ms},
        )
        # 强制输出堆栈到 stdout（避免 uvicorn/logger 配置导致 traceback 不可见）
        print(traceback.format_exc(), flush=True)
        _logger.error(
            'unhandled_exception_detail type=%s module=%s message=%s',
            type(e).__name__,
            type(e).__module__,
            str(e),
        )
        print(
            f'unhandled_exception method={request.method} path={request.url.path} cost_ms={cost_ms} '
            f'type={type(e).__name__} module={type(e).__module__} message={e}',
            flush=True,
        )
        return JSONResponse(status_code=500, content={'code': 500, 'message': 'Internal Server Error', 'data': None})
    cost_ms = int((time.time() - start) * 1000)
    if response.status_code >= 500:
        _logger.error(
            'access-log method=%s path=%s status=%s cost_ms=%d',
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
            extra={
                'method': request.method,
                'path': request.url.path,
                'status': response.status_code,
                'cost_ms': cost_ms,
            },
        )
        print(
            f'access-log method={request.method} path={request.url.path}'
            f' status={response.status_code} cost_ms={cost_ms}',
            flush=True,
        )
    else:
        _logger.info(
            'access-log method=%s path=%s status=%s cost_ms=%d',
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
            extra={
                'method': request.method,
                'path': request.url.path,
                'status': response.status_code,
                'cost_ms': cost_ms,
            },
        )
        print(
            f'access-log method={request.method} path={request.url.path}'
            f' status={response.status_code} cost_ms={cost_ms}',
            flush=True,
        )
    return response


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

    if isinstance(payload, dict) and (
        ('swagger' in payload or 'openapi' in payload)
        and 'info' in payload
        and 'paths' in payload
    ):
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


@app.exception_handler(redis.exceptions.RedisError)
def _handle_redis_error(_, exc: redis.exceptions.RedisError):
    from core.errors import ErrorCodes, raise_error
    # 这里必须打印完整堆栈，否则容器日志只剩 "Redis 认证失败" 无法定位根因。
    tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    _logger.error('redis_error type=%s message=%s\n%s', type(exc).__name__, str(exc), tb)
    print(f'redis_error type={type(exc).__name__} message={exc}\n{tb}', flush=True)
    try:
        if isinstance(exc, redis.exceptions.AuthenticationError):
            raise_error(ErrorCodes.REDIS_AUTH_FAILED)
        raise_error(ErrorCodes.REDIS_UNAVAILABLE)
    except AppException as e:
        return JSONResponse(status_code=e.http_code, content=error_payload_from_exception(e))


@app.exception_handler(StarletteHTTPException)
def _handle_http_exception(_, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else 'HTTP error'
    return JSONResponse(
        status_code=exc.status_code,
        content={'code': exc.status_code, 'message': message, 'data': None},
    )


@app.exception_handler(RequestValidationError)
def _handle_validation_error(_, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={'code': 400, 'message': '参数错误', 'data': exc.errors()})


def _export_openapi_artifacts() -> None:
    schema = app.openapi()
    current_dir = Path(__file__).resolve().parent
    repo_root = current_dir.parent.parent
    outputs = {
        current_dir / 'openapi.json': 'json',
        repo_root / 'api' / 'backend' / 'auth-service' / 'swagger.json': 'json',
        repo_root / 'api' / 'backend' / 'auth-service' / 'openapi.yml': 'yaml',
        Path('/openapi-export/auth-service/swagger.json'): 'json',
        Path('/openapi-export/auth-service/openapi.yml'): 'yaml',
    }
    json_body = json.dumps(schema, ensure_ascii=False, indent=2) + '\n'
    yaml_body = yaml.dump(schema, allow_unicode=True, sort_keys=False)
    for output, kind in outputs.items():
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            if kind == 'json':
                output.write_text(json_body, encoding='utf-8')
            else:
                output.write_text(yaml_body, encoding='utf-8')
        except OSError:
            continue


@app.get(_SWAGGER_JSON_PATH, include_in_schema=False)
def swagger_json():
    return JSONResponse(content=app.openapi())


@app.get(_OPENAPI_YAML_PATH, include_in_schema=False)
def openapi_yaml():
    """openapi.yaml文档"""
    schema = app.openapi()
    body = yaml.dump(schema, allow_unicode=True, sort_keys=False)
    return Response(content=body, media_type='application/x-yaml')


app.include_router(auth_router, prefix=_API_PREFIX)
app.include_router(authorization_router, prefix=_API_PREFIX)
app.include_router(user_router, prefix=_API_PREFIX)
app.include_router(role_router, prefix=_API_PREFIX)
app.include_router(group_router, prefix=_API_PREFIX)

_export_openapi_artifacts()
