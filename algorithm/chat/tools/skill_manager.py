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
from chat.tools.memory import (
    MAX_SUGGESTIONS_PER_CALL,
    Suggestion,
    _agentic_config,
    _post_core_api,
    _session_id,
)

_PATH_SEGMENT_RE = re.compile(r'^[A-Za-z0-9._-]+$')
_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
_MAX_DESCRIPTION_LENGTH = 1024


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


def _validate_skill_name(name: str) -> Optional[str]:
    if not name or not name.strip():
        return "'name' must be a non-empty skill name."
    if name in {'.', '..'} or not _PATH_SEGMENT_RE.match(name):
        return (
            f"Skill name {name!r} is invalid; only ASCII letters, digits, "
            "'-', '_' and '.' are allowed (no spaces, no Chinese, no slashes)."
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
        return "action='create' requires a non-empty 'content' (full SKILL.md body)."

    frontmatter, body = _parse_frontmatter(content)
    if not frontmatter:
        return 'SKILL.md must contain YAML frontmatter.'
    if 'name' not in frontmatter:
        return "Frontmatter must include 'name'."
    if 'description' not in frontmatter:
        return "Frontmatter must include 'description'."
    if len(str(frontmatter.get('description', ''))) > _MAX_DESCRIPTION_LENGTH:
        return f'Description exceeds {_MAX_DESCRIPTION_LENGTH} characters.'
    if not body.strip():
        return 'SKILL.md must have markdown content after frontmatter.'
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

    return '/'.join(parts)

def list_all_skills_with_category(
    skill_fs_url: str,
) -> Dict[str, str]:
    manager = LazySkillManager(dir=skill_fs_url, fs=FS)
    manager._load_skills_index()
    results: Dict[str, str] = {}
    for name, info in manager._skills_index.items():
        results[name] = _extract_category_from_path(info.get('path', ''), name)
    return results


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def skill_manage(
    name: str,
    action: Literal['create', 'modify', 'remove'],
    category: Optional[str] = '',
    content: Optional[str] = None,
    suggestions: Optional[List[Suggestion]] = None,
) -> Dict[str, Any]:
    """Manage skills by creating, modifying, or removing a skill entry.

    Args:
        name: Skill name.
        action: Action to perform.
        category: Skill category directory.
        content: Full SKILL.md content when creating a skill.
        suggestions: Suggestions when modifying a skill.
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
        return _fail("'session_id' is required in agentic_config.")

    existing_skills = list_all_skills_with_category(agentic_config.get('skill_fs_url') or '')

    if action == 'create':
        content_error = _validate_skill_content(content or '')
        if content_error:
            return _fail(content_error)
        if suggestions:
            return _fail("action='create' must not include 'suggestions'.")
        if name in existing_skills:
            return _fail(
                f"Skill {name!r} already exists; use action='modify' to edit it "
                "or action='remove' to delete it first."
            )

        normalized_category = _normalize_category(category)
        if normalized_category is None:
            return _fail(
                f"Category {category!r} is invalid; it must be a single "
                "ASCII-safe path segment (only letters, digits, '-', '_' "
                "and '.'; no spaces, no Chinese, no '/')."
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
            return _fail(f'Failed to create skill: {exc}')
        return _ok(result)

    if action == 'modify':
        if content is not None:
            return _fail("action='modify' must not include 'content'; use 'suggestions'.")
        if not suggestions:
            return _fail("action='modify' requires a non-empty 'suggestions' list.")
        if len(suggestions) > MAX_SUGGESTIONS_PER_CALL:
            return _fail(
                f'At most {MAX_SUGGESTIONS_PER_CALL} suggestions are allowed per call; '
                f'got {len(suggestions)}.'
            )
        if name not in existing_skills:
            return _fail(
                f"Skill {name!r} does not exist; use action='create' to add a new skill."
            )

        resolved_category = existing_skills[name]
        result = {
            'name': name,
            'action': action,
            'category': resolved_category,
            'suggestions': list(suggestions),
        }
        payload = {
            'session_id': session_id,
            'skill_name': name,
            'category': resolved_category,
            'suggestions': [dict(s) for s in suggestions],
        }
        try:
            result.update(_post_core_api('/skill/suggestion', payload))
        except (requests.RequestException, RuntimeError) as exc:
            return _fail(f'Failed to submit skill suggestions: {exc}')
        return _ok(result)

    if action == 'remove':
        if content is not None or suggestions:
            return _fail("action='remove' must not include 'content' or 'suggestions'.")
        if name not in existing_skills:
            return _fail(f"Skill {name!r} does not exist; nothing to remove.")

        resolved_category = existing_skills[name]
        result = {
            'name': name,
            'action': action,
            'category': resolved_category,
        }
        payload = {
            'session_id': session_id,
            'skill_name': name,
            'category': resolved_category,
        }
        try:
            result.update(_post_core_api('/skill/remove', payload))
        except (requests.RequestException, RuntimeError) as exc:
            return _fail(f'Failed to remove skill: {exc}')
        return _ok(result)

    return _fail(f"Unknown action {action!r}; expected one of 'create', 'modify', 'remove'.")
