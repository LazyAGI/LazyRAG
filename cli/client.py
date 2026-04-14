"""HTTP client with automatic Bearer-token injection and token refresh."""

import json
import mimetypes
import sys
import tempfile
import uuid
from typing import Any, BinaryIO, Dict, List, Optional, Tuple
from urllib import error, request

from cli import credentials
from cli.config import AUTH_API_PREFIX, DEFAULT_SERVER_URL


class ApiError(RuntimeError):
    """Raised when the server returns a non-success response."""

    def __init__(
        self,
        status_code: int,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code, message, payload or {})
        self.status_code = status_code
        self.payload = payload or {}

    def __str__(self) -> str:
        return str(self.args[1])


# ---------------------------------------------------------------------------
# low-level helpers
# ---------------------------------------------------------------------------

def _decode_body(body: bytes) -> Dict[str, Any]:
    text = body.decode('utf-8', errors='replace').strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid JSON response: {text}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'Unexpected response type: {type(payload).__name__}')
    return payload


def _build_api_error(
    status_code: int,
    response_body: bytes,
    default_message: str,
) -> ApiError:
    try:
        parsed = _decode_body(response_body)
    except RuntimeError:
        text = response_body.decode('utf-8', errors='replace').strip()
        return ApiError(status_code, text or default_message)
    message = (
        parsed.get('message')
        or parsed.get('msg')
        or parsed.get('detail')
        or default_message
    )
    return ApiError(status_code, str(message), parsed)


def _normalize_response_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap service envelopes while preserving error semantics."""
    code = parsed.get('code')
    if not isinstance(code, int) or 'message' not in parsed:
        return parsed

    if code not in (0, 200):
        raise ApiError(
            code,
            str(parsed.get('message') or 'request failed'),
            parsed,
        )

    data = parsed.get('data')
    if isinstance(data, dict):
        return data
    if data is None:
        return {}
    return {'data': data}


# ---------------------------------------------------------------------------
# generic request
# ---------------------------------------------------------------------------

def raw_request(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Send an HTTP request and return the parsed JSON response dict."""
    req_headers: Dict[str, str] = {'Accept': 'application/json'}
    if headers:
        req_headers.update(headers)

    data = body
    if data is None and payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req_headers.setdefault('Content-Type', 'application/json')

    req = request.Request(
        url=url, data=data, headers=req_headers, method=method.upper(),
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read()
    except error.HTTPError as exc:
        resp_body = exc.read()
        raise _build_api_error(
            exc.code, resp_body, str(exc.reason or f'HTTP {exc.code}'),
        )
    except error.URLError as exc:
        raise RuntimeError(f'Cannot reach {url}: {exc}') from exc

    parsed = _decode_body(resp_body)
    return _normalize_response_payload(parsed)


# ---------------------------------------------------------------------------
# server URL resolution
# ---------------------------------------------------------------------------

def resolve_server_url(cli_url: Optional[str] = None) -> str:
    """Pick server URL: CLI flag > stored credential > env/default."""
    if cli_url:
        return cli_url.rstrip('/')
    stored = credentials.server_url()
    if stored:
        return stored.rstrip('/')
    return DEFAULT_SERVER_URL.rstrip('/')


# ---------------------------------------------------------------------------
# token refresh
# ---------------------------------------------------------------------------

def _try_refresh(server: str) -> bool:
    """Attempt to refresh the access token.  Returns True on success."""
    rt = credentials.refresh_token()
    if not rt:
        return False
    url = f'{server}{AUTH_API_PREFIX}/refresh'
    try:
        data = raw_request('POST', url, payload={'refresh_token': rt})
    except (ApiError, RuntimeError):
        return False
    creds = credentials.load() or {}
    creds.update({
        'access_token': data['access_token'],
        'refresh_token': data['refresh_token'],
        'expires_in': data.get('expires_in', 0),
        'server_url': server,
    })
    credentials.save(creds)
    return True


# ---------------------------------------------------------------------------
# authenticated requests
# ---------------------------------------------------------------------------

def _auth_headers(token: str) -> Dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def auth_request(
    method: str,
    path: str,
    server: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Any] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Like *raw_request* but injects the stored Bearer token.

    Automatically refreshes the token once if it looks expired.
    """
    server = resolve_server_url(server)
    token = credentials.access_token()
    if token is None:
        print('Not logged in. Run `lazyrag login` first.', file=sys.stderr)
        raise SystemExit(1)

    if credentials.is_token_expired():
        if not _try_refresh(server):
            print(
                'Session expired.  Run `lazyrag login` to re-authenticate.',
                file=sys.stderr,
            )
            raise SystemExit(1)
        token = credentials.access_token()

    url = f'{server}{path}'
    hdrs = _auth_headers(token)
    if headers:
        hdrs.update(headers)

    try:
        return raw_request(method, url, payload=payload, headers=hdrs,
                           body=body, timeout=timeout)
    except ApiError as exc:
        if exc.status_code == 401:
            # one retry after refresh
            if _try_refresh(server):
                token = credentials.access_token()
                hdrs = _auth_headers(token)
                if headers:
                    hdrs.update(headers)
                return raw_request(method, url, payload=payload, headers=hdrs,
                                   body=body, timeout=timeout)
            print(
                'Session expired.  Run `lazyrag login` to re-authenticate.',
                file=sys.stderr,
            )
            raise SystemExit(1)
        raise


# ---------------------------------------------------------------------------
# multipart upload helper
# ---------------------------------------------------------------------------

def build_multipart_body(
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    file_content: bytes,
) -> Tuple[bytes, Dict[str, str]]:
    """Build a multipart/form-data body with one file."""
    boundary = f'----LazyRAGBoundary{uuid.uuid4().hex}'
    parts: List[bytes] = []

    for key, value in fields.items():
        parts.append(f'--{boundary}\r\n'.encode())
        parts.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
        )
        parts.append(str(value).encode('utf-8'))
        parts.append(b'\r\n')

    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    parts.append(f'--{boundary}\r\n'.encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\n'.encode(),
    )
    parts.append(f'Content-Type: {content_type}\r\n\r\n'.encode())
    parts.append(file_content)
    parts.append(b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())

    body = b''.join(parts)
    return body, {'Content-Type': f'multipart/form-data; boundary={boundary}'}


def build_multipart_file(
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    source_path: str,
) -> Tuple[BinaryIO, Dict[str, str]]:
    """Build a multipart/form-data payload backed by a temp file."""
    boundary = f'----LazyRAGBoundary{uuid.uuid4().hex}'
    handle = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)

    def _write(chunk: bytes) -> None:
        handle.write(chunk)

    for key, value in fields.items():
        _write(f'--{boundary}\r\n'.encode())
        _write(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
        )
        _write(str(value).encode('utf-8'))
        _write(b'\r\n')

    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    _write(f'--{boundary}\r\n'.encode())
    _write(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\n'.encode(),
    )
    _write(f'Content-Type: {content_type}\r\n\r\n'.encode())

    with open(source_path, 'rb') as src:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            _write(chunk)

    _write(b'\r\n')
    _write(f'--{boundary}--\r\n'.encode())
    size = handle.tell()
    handle.seek(0)
    return handle, {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(size),
    }


def auth_upload(
    path: str,
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    source_path: str,
    server: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Upload a file via multipart/form-data with Bearer auth."""
    body, hdrs = build_multipart_file(fields, file_field, filename, source_path)
    try:
        return auth_request(
            'POST', path, server=server, headers=hdrs, body=body, timeout=timeout,
        )
    finally:
        body.close()


# ---------------------------------------------------------------------------
# printing helpers
# ---------------------------------------------------------------------------

def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))
