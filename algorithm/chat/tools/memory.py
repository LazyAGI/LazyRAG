from functools import wraps
from typing import Any, Dict, List, Literal, Optional

import lazyllm
import requests
from lazyllm import fc_register
from typing_extensions import TypedDict


MAX_SUGGESTIONS_PER_CALL = 5
DEFAULT_CORE_API_TIMEOUT = 30

_TARGET_FILENAMES: Dict[str, str] = {
    'memory': 'memory.jsonl',
    'user': 'user.jsonl',
}


def _tool_failure(tool_name: str, exc: Exception) -> Dict[str, Any]:
    return {
        'success': False,
        'reason': f'{tool_name} 执行失败：{exc}',
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
    """供 skill / memory / user_preference 共用的自然语言修改建议。

    字段：
        title (str, 必填): 对修改建议的简短标题。
        content (str, 必填): 对修改内容的自然语言说明；下游审查/合并流程会据此应用修改。
        reason (str, 可选): 说明为什么该修改值得保存。
    """

    title: str
    content: str
    reason: str


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
        raise RuntimeError(f'POST {url} 请求失败，HTTP 状态码 {response.status_code}：{msg}')

    if isinstance(body, dict) and body.get('code') not in (None, 0):
        msg = body.get('msg') or body.get('message') or body
        raise RuntimeError(f'POST {url} 请求失败：{msg}')

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
    """为用户长期记忆（``target='memory'``）或用户画像/偏好（``target='user'``）记录自然语言修改建议。

    当你在处理当前问题时学到某些应当**跨未来会话持久保留**的信息时，调用该工具。
    例如：关于用户的稳定事实、用户偏好，或智能体下次应记住的长期工作记忆条目。
    每次调用最多提交 5 条建议；每条建议只描述一个修改点，并会在合并前经过审查。

    不要用该工具保存一次性对话笔记、回答当前问题的内容，或把最终回复原样回写给用户。

    参数：
        target: 建议所属的缓冲区。``'memory'`` 表示智能体自己的长期工作记忆；
            ``'user'`` 表示用户画像/偏好文本。
        suggestions: 有序建议列表（每次最多 5 条）。每个元素是包含以下字段的字典：

            - ``title`` (str, 必填): 对修改建议的简短标题。
            - ``content`` (str, 必填): 对修改内容的自然语言说明。
            - ``reason`` (str, 可选): 说明为什么需要该修改。

    返回：
        带有成功状态的结构化结果。

        - 成功: ``{'success': True, 'result': {...}}``
        - 失败: ``{'success': False, 'reason': '...'}``
    """
    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        return {'success': True, 'result': result}

    def _fail(reason: str) -> Dict[str, Any]:
        return {'success': False, 'reason': reason}

    if target not in _TARGET_FILENAMES:
        return _fail(
            f"未知 target：{target!r}；应为 'memory' 或 'user'。"
        )
    if not suggestions:
        return _fail("'suggestions' 必须是非空列表。")
    if len(suggestions) > MAX_SUGGESTIONS_PER_CALL:
        return _fail(
            f'每次最多允许提交 {MAX_SUGGESTIONS_PER_CALL} 条 suggestions；'
            f'当前收到 {len(suggestions)} 条。'
        )

    agentic_config = _agentic_config()
    session_id = _session_id(agentic_config)
    if not session_id:
        return _fail("agentic_config 中缺少必需的 'session_id'。")

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
        lazyllm.LOG.error(f'提交 memory 建议失败：{exc}')
        return _fail(f'提交 memory 建议失败：{exc}')

    return _ok(result)
