from functools import wraps
from typing import Any, Dict, List, Literal, Optional

import lazyllm
import requests
from lazyllm import fc_register
from typing_extensions import TypedDict


MAX_SUGGESTIONS_PER_CALL = 5
DEFAULT_CORE_API_URL = 'http://10.119.24.129:9090'
DEFAULT_CORE_API_TIMEOUT = 30

_TARGET_FILENAMES: Dict[str, str] = {
    'memory': 'memory.jsonl',
    'user': 'user.jsonl',
}


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


class Suggestion(TypedDict, total=False):
    """Natural-language edit suggestion shared by skill / memory / user_preference.

    Fields:
        title (str, required): short label summarising the proposed change.
        content (str, required): natural-language description of the
            modification; the downstream reviewer applies it.
        reason (str, optional): why the change is worth making.
    """

    title: str
    content: str
    reason: str


def _agentic_config() -> Dict[str, Any]:
    config = lazyllm.globals.get('agentic_config') or {}
    return config if isinstance(config, dict) else {}


def _core_api_base_url(agentic_config: Optional[Dict[str, Any]] = None) -> str:
    config = agentic_config if isinstance(agentic_config, dict) else _agentic_config()
    return str(config.get('core_api_url') or DEFAULT_CORE_API_URL).rstrip('/')


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


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def memory(
    target: Literal['memory', 'user'],
    suggestions: List[Suggestion],
) -> Dict[str, Any]:
    """Record natural-language edit suggestions for the user's long-term
    memory (``target='memory'``) or user profile / preference
    (``target='user'``).

    Call this tool when, while handling the current query, you learn
    something that should persist **across future sessions** — e.g. stable
    facts about the user, their preferences, or durable working-memory
    items the agent should remember next time. Each call accepts a batch
    of at most 5 suggestions; every suggestion describes ONE change in
    natural language and will be reviewed before being merged.

    Do **not** use this tool for one-off conversational notes, for
    answering the current query, or to echo the final response back to
    the user.

    Args:
        target: Which buffer the suggestions belong to. ``'memory'`` is the
            agent's own long-term working memory; ``'user'`` is the user
            profile / preference text.
        suggestions: Ordered list of suggestions (max 5 per call). Each
            item is a dict with the following fields:

            - ``title`` (str, required): short label summarising the change.
            - ``content`` (str, required): natural-language description of
              the modification.
            - ``reason`` (str, optional): rationale for the change.

    Returns:
        A structured result with success status.

        - success: ``{'success': True, 'result': {...}}``
        - failure: ``{'success': False, 'reason': '...'}``
    """
    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        return {'success': True, 'result': result}

    def _fail(reason: str) -> Dict[str, Any]:
        return {'success': False, 'reason': reason}

    if target not in _TARGET_FILENAMES:
        return _fail(
            f"Unknown target {target!r}; expected one of 'memory', 'user'."
        )
    if not suggestions:
        return _fail("'suggestions' must be a non-empty list.")
    if len(suggestions) > MAX_SUGGESTIONS_PER_CALL:
        return _fail(
            f'At most {MAX_SUGGESTIONS_PER_CALL} suggestions are allowed per '
            f'call; got {len(suggestions)}.'
        )

    agentic_config = _agentic_config()
    session_id = _session_id(agentic_config)
    if not session_id:
        return _fail("'session_id' is required in agentic_config.")

    endpoint = (
        '/memory/suggestion'
        if target == 'memory'
        else '/user_preference/suggestion'
    )
    payload = {
        'session_id': session_id,
        'suggestions': [dict(s) for s in suggestions],
    }

    result: Dict[str, Any] = {
        'target': target,
        'appended_suggestions': len(suggestions),
    }
    try:
        result.update(_post_core_api(endpoint, payload))
    except (requests.RequestException, RuntimeError) as exc:
        lazyllm.LOG.error(f'Failed to submit memory suggestions: {exc}')
        return _fail(f'Failed to submit memory suggestions: {exc}')

    return _ok(result)
