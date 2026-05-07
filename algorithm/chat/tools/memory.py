from functools import wraps
from typing import Any, Dict, Literal, Optional

import lazyllm
import requests
from lazyllm import fc_register


MAX_CONTENT_CHARS = 1500
DEFAULT_CORE_API_TIMEOUT = 30


def _tool_failure(tool_name: str, exc: Exception) -> Dict[str, Any]:
    return {
        'success': False,
        'reason': f'{tool_name} failed: {exc}',
        'error': str(exc),
        'error_type': type(exc).__name__,
    }


def _handle_tool_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return _tool_failure(func.__name__, exc)

    return wrapper


def _agentic_config() -> Dict[str, Any]:
    config = lazyllm.globals.get('agentic_config') or {}
    return config if isinstance(config, dict) else {}


def _core_api_base_url(agentic_config: Optional[Dict[str, Any]] = None) -> str:
    config = agentic_config if isinstance(agentic_config, dict) else _agentic_config()
    return str(config.get('core_api_url'))


def _core_api_endpoint(path: str, agentic_config: Optional[Dict[str, Any]] = None) -> str:
    base_url = _core_api_base_url(agentic_config)
    normalized_path = '/' + path.lstrip('/')
    return f'{base_url}{normalized_path}'


def _session_id(agentic_config: Optional[Dict[str, Any]] = None) -> str:
    config = agentic_config if isinstance(agentic_config, dict) else _agentic_config()
    return str(config.get('session_id') or lazyllm.globals._sid or '').strip()


def _post_core_api(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    config = _agentic_config()
    url = _core_api_endpoint(path, config)
    timeout = config.get('core_api_timeout', DEFAULT_CORE_API_TIMEOUT)
    with requests.sessions.Session() as session:
        session.trust_env = False
        response = session.post(url, json=payload, timeout=timeout)

    try:
        body = response.json()
    except ValueError:
        body = {'text': response.text}

    if not response.ok:
        msg = (
            body.get('msg') or body.get('message')
            if isinstance(body, dict)
            else response.text
        )
        raise RuntimeError(f'POST {url} failed with HTTP {response.status_code}: {msg}')

    if isinstance(body, dict) and body.get('code') not in (None, 0):
        msg = body.get('msg') or body.get('message') or body
        raise RuntimeError(f'POST {url} failed: {msg}')

    return {
        'persisted': 'core_api',
        'url': url,
        'response': body,
    }


def _compact_content(text: str) -> str:
    return ''.join(str(text).split())


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def memory(
    target: Literal['memory', 'user'],
    content: str,
) -> Dict[str, Any]:
    """Directly overwrite the user's long-term memory or user_preference.

    Provide the COMPLETE new full text in ``content``. Do not send patch
    instructions, suggestions, or partial diffs. The tool writes the final
    content directly to the backend for the current session user.

    Use ``target='memory'`` for reusable experience, conclusions, and
    durable working knowledge. Use ``target='user'`` for long-term stable
    user preferences such as tone, language, structure, taboos, and default
    workflow conventions.

    Writing requirements:
    - ``content`` must be the full new text after your update.
    - Keep it structured and easy to scan.
    - Excluding whitespace and line breaks, the total length must not exceed
      1500 characters.
    - Do not use this tool for one-off conversation notes or transient logs.

    Args:
        target: ``'memory'`` updates managed memory; ``'user'`` updates
            managed user_preference.
        content: The new full text to persist.
    """
    def _ok(normalized_target: str) -> Dict[str, Any]:
        return {'success': True, 'target': normalized_target}

    def _fail(reason: str) -> Dict[str, Any]:
        return {'success': False, 'reason': reason}

    if target not in {'memory', 'user'}:
        return _fail(
            f"Unknown target {target!r}; expected one of 'memory', 'user'."
        )
    if not isinstance(content, str) or not content.strip():
        return _fail("'content' must be a non-empty string.")
    if len(_compact_content(content)) > MAX_CONTENT_CHARS:
        return _fail(
            f"'content' exceeds the {MAX_CONTENT_CHARS}-character limit "
            'after removing whitespace.'
        )

    agentic_config = _agentic_config()
    session_id = _session_id(agentic_config)
    if not session_id:
        return _fail("'session_id' is required in agentic_config.")

    endpoint = (
        '/memory/internal-upsert'
        if target == 'memory'
        else '/user_preference/internal-upsert'
    )
    payload = {
        'session_id': session_id,
        'content': content,
    }
    try:
        _post_core_api(endpoint, payload)
    except (requests.RequestException, RuntimeError) as exc:
        lazyllm.LOG.error(f'Failed to update managed memory: {exc}')
        return _fail(f'Failed to update managed memory: {exc}')

    return _ok(target)
