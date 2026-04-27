from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Tuple

from chat.prompts.agentic_v2 import (
    CITATION_GUIDANCE,
    DEFAULT_SYSTEM_PROMPT,
    MEMORY_GUIDANCE,
    SEARCH_GUIDANCE,
    SKILLS_GUIDANCE,
    TOOL_CALL_STATUS_GUIDANCE,
    _COMBINED_REVIEW_PROMPT,
    _MEMORY_REVIEW_PROMPT,
    _SKILL_REVIEW_PROMPT,
)
from chat.utils.load_config import load_model_config

DEFAULT_TOOLS = [
    'kb_search',
    'kb_get_parent_node',
    'kb_get_window_nodes',
    'kb_keyword_search',
    'web_search',
    'url_fetch',
    'arxiv_search',
    'memory',
    'skill_manage',
]

BUILTIN_FILE_TOOLS = (
    'read_file',
    'list_dir',
    'search_in_files',
    'make_dir',
    'write_file',
    'delete_file',
    'move_file',
)

REVIEW_TOOLS: dict[str, list[str]] = {
    'memory': ['memory'],
    'skill': ['skill_manage'],
    'combined': ['memory', 'skill_manage'],
}

REVIEW_PROMPTS: dict[str, str] = {
    'memory': _MEMORY_REVIEW_PROMPT,
    'skill': _SKILL_REVIEW_PROMPT,
    'combined': _COMBINED_REVIEW_PROMPT,
}


def _normalize_available_tools(tools: Any) -> list[str]:
    if tools is None:
        return list(DEFAULT_TOOLS)
    if isinstance(tools, str):
        tools = [tools]
    if not isinstance(tools, list):
        return list(DEFAULT_TOOLS)
    if any(isinstance(t, str) and t.lower() == 'all' for t in tools):
        return list(DEFAULT_TOOLS)
    return [t for t in tools if isinstance(t, str) and t]


def _merge_builtin_file_tools(tools: list[str]) -> list[str]:
    merged: list[str] = []
    seen_names: set[str] = set()

    for tool in tools:
        if not isinstance(tool, str) or not tool:
            continue
        tool_name = tool.rsplit('.', 1)[-1]
        if tool_name in seen_names:
            continue
        seen_names.add(tool_name)
        merged.append(tool)

    for tool_name in BUILTIN_FILE_TOOLS:
        if tool_name in seen_names:
            continue
        seen_names.add(tool_name)
        merged.append(tool_name)

    return merged


def _normalize_available_skills(skills: Any) -> list[str]:
    if skills is None:
        return []
    if isinstance(skills, str):
        skills = [skills]
    if not isinstance(skills, list):
        return []
    return [skill for skill in skills if isinstance(skill, str) and skill]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == '':
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_dataset_url(dataset_url: str) -> Tuple[str, str]:
    parts = [p.strip() for p in str(dataset_url).split(',', 1)]
    kb_url = parts[0] if parts else ''
    kb_name = parts[1] if len(parts) > 1 else ''
    return kb_url, kb_name


def _sync_request_context(config: dict) -> None:
    filters = config.get('filters') if isinstance(config.get('filters'), dict) else {}
    kb_id = str(filters.get('kb_id') or config.get('kb_id') or '').strip()
    if kb_id:
        config['kb_id'] = kb_id
    else:
        config.pop('kb_id', None)

    files = config.get('files') or []
    config['temp_files'] = files if isinstance(files, list) else []

    kb_url, kb_name = _parse_dataset_url(config.get('document_url') or '')
    if kb_url:
        config['kb_url'] = kb_url
    if kb_name:
        config['kb_name'] = kb_name


def _filter_tools_for_request(tools: list[str], config: dict) -> list[str]:
    if config.get('kb_id'):
        return tools

    has_temp_files = bool(config.get('temp_files'))
    filtered = []
    for tool in tools:
        if not tool.startswith('kb_'):
            filtered.append(tool)
        elif has_temp_files and tool == 'kb_search':
            filtered.append(tool)
    return filtered


def _with_agentic_defaults(config: dict) -> dict:
    defaults = {
        'available_tools': DEFAULT_TOOLS,
        'available_skills': [],
        'skill_fs_url': '.agentic_rag/skills',
        'memory_fs_dir': '.agentic_rag/memory',
        'core_api_url': os.getenv('LAZYRAG_CORE_API_URL', 'http://core:8000'),
        'workspace': './workspace',
        'web_search_timeout': 10,
        'url_fetch_timeout': 10,
        'url_fetch_max_length': 4000,
        'web_search_auto_sources': ['bocha', 'google', 'bing', 'wikipedia'],
        'web_search_wikipedia_base_url': os.getenv(
            'LAZYRAG_WEB_SEARCH_WIKIPEDIA_BASE_URL', 'https://zh.wikipedia.org'
        ),
        'web_search_google_api_key': os.getenv('LAZYRAG_WEB_SEARCH_GOOGLE_API_KEY', ''),
        'web_search_google_search_engine_id': os.getenv(
            'LAZYRAG_WEB_SEARCH_GOOGLE_SEARCH_ENGINE_ID', ''
        ),
        'web_search_bing_subscription_key': os.getenv(
            'LAZYRAG_WEB_SEARCH_BING_SUBSCRIPTION_KEY', ''
        ),
        'web_search_bing_endpoint': os.getenv('LAZYRAG_WEB_SEARCH_BING_ENDPOINT', ''),
        'web_search_bocha_api_key': os.getenv('LAZYRAG_WEB_SEARCH_BOCHA_API_KEY', ''),
        'web_search_bocha_base_url': os.getenv(
            'LAZYRAG_WEB_SEARCH_BOCHA_BASE_URL', 'https://api.bochaai.com'
        ),
        'arxiv_search_timeout': 15,
    }
    for key, value in defaults.items():
        if config.get(key) is None:
            config[key] = value
    return config


def _build_runtime_system_prompt(config: dict, available_tools: list[str]) -> str:
    prompt_parts = [DEFAULT_SYSTEM_PROMPT]

    tool_guidance: list[str] = []
    if 'memory' in available_tools and config.get('use_memory', True):
        tool_guidance.append(MEMORY_GUIDANCE)
    if 'skill_manage' in available_tools:
        tool_guidance.append(SKILLS_GUIDANCE)
    if tool_guidance:
        prompt_parts.append(' '.join(tool_guidance))
    if available_tools:
        prompt_parts.append(TOOL_CALL_STATUS_GUIDANCE)
    if any(tool.startswith('kb_') for tool in available_tools):
        prompt_parts.append(CITATION_GUIDANCE)
    if (
        'web_search' in available_tools
        or 'arxiv_search' in available_tools
        or 'url_fetch' in available_tools
    ):
        prompt_parts.append(SEARCH_GUIDANCE)

    return '\n\n'.join(prompt_parts)


@lru_cache(maxsize=1)
def _get_runtime_agent_defaults() -> Dict[str, Any]:
    config = load_model_config()
    defaults = config.get('agentic_v2', {})
    return dict(defaults) if isinstance(defaults, dict) else {}
