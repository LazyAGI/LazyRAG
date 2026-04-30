import os
import re
import sys
from functools import wraps
from typing import Any, Dict, List, Literal, Optional

import requests
from lazyllm import fc_register
from lazyllm.tools.agent.skill_manager import SkillManager as LazySkillManager

if __package__ in (None, ''):
    _algorithm_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if _algorithm_root not in sys.path:
        sys.path.insert(0, _algorithm_root)

from lazyllm.tools.fs.client import FS
from common.remote_fs import RemoteFileSystem  # noqa: F401
from chat.tools.memory import (
    MAX_SUGGESTIONS_PER_CALL,
    Suggestion,
    _agentic_config,
    _post_core_api,
    _session_id,
)

_PATH_SEGMENT_RE = re.compile(r'^[A-Za-z0-9._-]+$')
_UUID_SEGMENT_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)
_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
_MAX_DESCRIPTION_LENGTH = 1024


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


def _validate_skill_name(name: str) -> Optional[str]:
    if not name or not name.strip():
        return "'name' 必须是非空技能名称。"
    if name in {'.', '..'} or not _PATH_SEGMENT_RE.match(name):
        return (
            f'技能名称 {name!r} 无效；只能包含 ASCII 字母、数字、'
            "'-'、'_' 和 '.'（不能有空格、中文或斜杠）。"
        )
    return None


def _normalize_category(category: Optional[str]) -> Optional[str]:
    if category is None:
        return ''
    cleaned = str(category).strip().strip('/')
    if not cleaned:
        return ''
    if cleaned in {'.', '..'} or not _PATH_SEGMENT_RE.match(cleaned):
        return None
    return cleaned


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(content or '')
    if not match:
        return {}, content or ''

    yaml_text, body = match.group(1), match.group(2)
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(yaml_text)
        if isinstance(parsed, dict):
            return parsed, body
    except Exception:
        pass

    return {}, body


def _validate_skill_content(content: str) -> Optional[str]:
    if not content or not content.strip():
        return "action='create' 需要提供非空 'content'（完整 SKILL.md 正文）。"

    frontmatter, body = _parse_frontmatter(content)
    if not frontmatter:
        return 'SKILL.md 必须包含 YAML frontmatter。'
    if 'name' not in frontmatter:
        return "Frontmatter 必须包含 'name'。"
    if 'description' not in frontmatter:
        return "Frontmatter 必须包含 'description'。"
    if len(str(frontmatter.get('description', ''))) > _MAX_DESCRIPTION_LENGTH:
        return f'description 超过 {_MAX_DESCRIPTION_LENGTH} 个字符。'
    if not body.strip():
        return 'SKILL.md 在 frontmatter 后必须包含 markdown 正文。'
    return None


def _extract_category_from_path(skill_dir: str, skill_name: str) -> str:
    path = str(skill_dir or '').rstrip('/')
    marker = '/skills/'

    if marker in path:
        tail = path.split(marker, 1)[1]
    else:
        tail = path.strip('/')

    parts = [p for p in tail.split('/') if p and p not in {'.'}]
    if not parts:
        return ''

    if parts[-1] == skill_name:
        parts = parts[:-1]

    if parts and _UUID_SEGMENT_RE.match(parts[0]):
        parts = parts[1:]

    return parts[-1] if parts else ''


def _skill_identity(category: str, skill_name: str) -> str:
    return f'{category}/{skill_name}' if category else skill_name


def list_all_skill_entries(
    skill_fs_url: str,
) -> Dict[str, Dict[str, str]]:
    manager = LazySkillManager(dir=skill_fs_url, fs=FS)
    results: Dict[str, Dict[str, str]] = {}

    for skill_dir, skill_md in manager._iter_skill_files():
        if manager._fs_getsize(skill_md) > manager._max_skill_md_bytes:
            continue
        try:
            content = manager._fs_read(skill_md)
        except Exception:
            continue

        meta = manager._extract_yaml_meta(content)
        if not manager._is_meta_valid(meta):
            continue

        name = str(meta.get('name') or '').strip()
        if not name:
            continue

        category = _extract_category_from_path(skill_dir, name)
        skill_id = _skill_identity(category, name)
        if skill_id in results:
            continue

        results[skill_id] = {
            'name': name,
            'category': category,
            'path': skill_dir,
        }
    return results


def list_all_skills_with_category(
    skill_fs_url: str,
) -> Dict[str, str]:
    results: Dict[str, str] = {}
    for info in list_all_skill_entries(skill_fs_url).values():
        results.setdefault(info['name'], info['category'])
    return results


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def skill_manage(
    name: str,
    action: Literal['create', 'modify', 'remove'],
    category: Optional[str],
    content: Optional[str] = None,
    suggestions: Optional[List[Suggestion]] = None,
) -> Dict[str, Any]:
    """通过创建、修改或删除技能条目来管理技能。

    参数：
        name: 技能名称。
        action: 要执行的操作。
        category: 技能所属类别目录。
        content: 创建技能时传入的完整 SKILL.md 内容。
        suggestions: 修改技能时传入的修改建议。
    """
    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        return {'success': True, 'result': result}

    def _fail(reason: str) -> Dict[str, Any]:
        return {'success': False, 'reason': reason}

    name_error = _validate_skill_name(name)
    if name_error:
        return _fail(name_error)

    agentic_config = _agentic_config()
    session_id = _session_id(agentic_config)
    if not session_id:
        return _fail("agentic_config 中缺少必需的 'session_id'。")

    normalized_category = _normalize_category(category)
    if normalized_category is None:
        return _fail(
            f'类别 {category!r} 无效；它必须是单层 ASCII 安全路径片段'
            "（只能包含字母、数字、'-'、'_' 和 '.'；不能有空格、中文或 '/'）。"
        )

    existing_skills = list_all_skill_entries(agentic_config.get('skill_fs_url') or '')
    skill_id = _skill_identity(normalized_category or '', name)

    if action == 'create':
        content_error = _validate_skill_content(content or '')
        if content_error:
            return _fail(content_error)
        if suggestions:
            return _fail("action='create' 不能包含 'suggestions'。")
        if skill_id in existing_skills:
            return _fail(
                f'技能 {name!r} 已存在于类别 {normalized_category!r} 中；'
                "请使用 action='modify' 修改它，或先用 action='remove' 删除它。"
            )

        result: Dict[str, Any] = {
            'name': name,
            'action': action,
            'category': normalized_category,
            'content': content,
        }
        payload = {
            'session_id': session_id,
            'category': normalized_category,
            'skill_name': name,
            'content': content,
        }
        try:
            result.update(_post_core_api('/skill/create', payload))
        except (requests.RequestException, RuntimeError) as exc:
            return _fail(f'创建技能失败：{exc}')
        return _ok(result)

    if action == 'modify':
        if content is not None:
            return _fail("action='modify' 不能包含 'content'；请使用 'suggestions'。")
        if not suggestions:
            return _fail("action='modify' 需要提供非空 'suggestions' 列表。")
        if len(suggestions) > MAX_SUGGESTIONS_PER_CALL:
            return _fail(
                f'每次最多允许提交 {MAX_SUGGESTIONS_PER_CALL} 条 suggestions；'
                f'当前收到 {len(suggestions)} 条。'
            )
        if skill_id not in existing_skills:
            return _fail(
                f'类别 {normalized_category!r} 中不存在技能 {name!r}；'
                "请使用 action='create' 新增技能。"
            )

        result = {
            'name': name,
            'action': action,
            'category': normalized_category,
            'suggestions': list(suggestions),
        }
        payload = {
            'session_id': session_id,
            'skill_name': name,
            'category': normalized_category,
            'suggestions': [dict(s) for s in suggestions],
        }
        try:
            result.update(_post_core_api('/skill/suggestion', payload))
        except (requests.RequestException, RuntimeError) as exc:
            return _fail(f'提交技能修改建议失败：{exc}')
        return _ok(result)

    if action == 'remove':
        if content is not None or suggestions:
            return _fail("action='remove' 不能包含 'content' 或 'suggestions'。")
        if skill_id not in existing_skills:
            return _fail(
                f'类别 {normalized_category!r} 中不存在技能 {name!r}；'
                '无需删除。'
            )

        result = {
            'name': name,
            'action': action,
            'category': normalized_category,
        }
        payload = {
            'session_id': session_id,
            'skill_name': name,
            'category': normalized_category,
        }
        try:
            result.update(_post_core_api('/skill/remove', payload))
        except (requests.RequestException, RuntimeError) as exc:
            return _fail(f'删除技能失败：{exc}')
        return _ok(result)

    return _fail(f"未知 action：{action!r}；应为 'create'、'modify' 或 'remove'。")
