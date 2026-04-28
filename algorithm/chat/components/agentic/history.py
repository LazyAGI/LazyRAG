from __future__ import annotations

import json
import re
from collections import OrderedDict
from html import escape
from typing import Any, Optional

from chat.components.agentic.tool_stream import (
    _TOOL_CALL_TAG,
    _TOOL_PREVIEW_TAG,
    _TOOL_RESULT_PREVIEW_TAG,
    _TOOL_RESULT_TAG,
)

_CITATION_REFS_KEY = '_citation_sources'
_CITATION_KEY_MAP_KEY = '_citation_key_map'
_CITATION_NEXT_KEY = '_citation_next_index'
_CITATION_PATTERN = re.compile(r'\[\[(\d+)\]\]')
_THINK_BLOCK_PATTERN = re.compile(r'<think>(.*?)</think>', re.DOTALL)
_HISTORY_TAG_PATTERN = re.compile(
    r'<(?P<tag>tp|trp|tool_call|tool_result)(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>',
    re.DOTALL,
)


def _history_message_content(message: dict[str, Any]) -> str:
    content = message.get('content')
    return content if isinstance(content, str) else ''


def _tool_result_message_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, separators=(',', ':'))


def _parse_history_assistant_content(content: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    cursor = 0

    for match in _HISTORY_TAG_PATTERN.finditer(content or ''):
        text_parts.append(content[cursor:match.start()])
        cursor = match.end()
        tag = match.group('tag')
        body = match.group('body') or ''
        if tag in (_TOOL_PREVIEW_TAG, _TOOL_RESULT_PREVIEW_TAG):
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if tag == _TOOL_CALL_TAG:
            tool_call_id = str(payload.get('id') or '')
            tool_name = str(payload.get('name') or '')
            if not tool_call_id or not tool_name:
                continue
            arguments = payload.get('arguments', {})
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append({
                'id': tool_call_id,
                'type': 'function',
                'function': {
                    'name': tool_name,
                    'arguments': json.dumps(arguments, ensure_ascii=False),
                },
            })
        elif tag == _TOOL_RESULT_TAG:
            tool_results.append({
                'id': str(payload.get('id') or ''),
                'name': str(payload.get('name') or ''),
                'result': payload.get('result'),
            })
    text_parts.append(content[cursor:])
    return ''.join(text_parts).strip(), tool_calls, tool_results


def _normalize_history_for_agent(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for message in history or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get('role') or '').strip()
        if role == 'assistant':
            content = _history_message_content(message)
            body_text, tool_calls, tool_results = _parse_history_assistant_content(content)
            assistant_message = {'role': 'assistant', 'content': body_text}
            if tool_calls:
                assistant_message['tool_calls'] = tool_calls
            normalized.append(assistant_message)

            valid_tool_call_ids = {
                str(tool_call.get('id') or '')
                for tool_call in tool_calls
                if str(tool_call.get('id') or '')
            }
            for tool_result in tool_results:
                tool_call_id = str(tool_result.get('id') or '')
                if not tool_call_id or tool_call_id not in valid_tool_call_ids:
                    continue
                normalized.append({
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'name': str(tool_result.get('name') or ''),
                    'content': _tool_result_message_content(tool_result.get('result')),
                })
            continue

        if role == 'user':
            content = _history_message_content(message)
            if content:
                normalized.append({'role': 'user', 'content': content})
            continue

        if role == 'tool':
            content = _history_message_content(message)
            normalized.append({
                'role': 'tool',
                'tool_call_id': str(message.get('tool_call_id') or ''),
                'name': str(message.get('name') or ''),
                'content': content,
            })
            continue

        content = _history_message_content(message)
        if content:
            normalized.append({'role': role or 'assistant', 'content': content})
    return normalized


def _reset_citation_state(config: dict) -> None:
    config[_CITATION_REFS_KEY] = {}
    config[_CITATION_KEY_MAP_KEY] = {}
    config[_CITATION_NEXT_KEY] = 1


def _citation_source(config: dict, index: int) -> Optional[dict[str, Any]]:
    refs = config.get(_CITATION_REFS_KEY)
    if not isinstance(refs, dict):
        return None
    source = refs.get(index) or refs.get(str(index))
    return source if isinstance(source, dict) else None


def _rewrite_citations(text: str, config: dict) -> tuple[str, list[dict[str, Any]]]:
    collected: OrderedDict[int, dict[str, Any]] = OrderedDict()

    def _replace(match: re.Match) -> str:
        index = int(match.group(1))
        source = _citation_source(config, index)
        if not source:
            return ''
        collected.setdefault(index, source)
        title = escape(str(source.get('file_name') or 'title'), quote=True)
        return f'[{index}](#source "{title}")'

    return _CITATION_PATTERN.sub(_replace, text), list(collected.values())


def _split_think_and_body(raw_text: str, existing_think: Any = '') -> tuple[str, str]:
    think_parts: list[str] = []
    if existing_think:
        think_parts.append(str(existing_think))

    def _collect_think(match: re.Match) -> str:
        think_parts.append(match.group(1))
        return ''

    body = _THINK_BLOCK_PATTERN.sub(_collect_think, raw_text or '')
    if '<think>' in body:
        before, after = body.split('<think>', 1)
        if '</think>' in after:
            think, rest = after.split('</think>', 1)
            think_parts.append(think)
            body = before + rest
        else:
            think_parts.append(after)
            body = before
    body = body.replace('</think>', '')
    think = '\n'.join(part.strip() for part in think_parts if str(part).strip())
    return think.strip(), body


def _format_non_stream_result(result: Any, config: dict) -> dict[str, Any]:
    if isinstance(result, dict):
        raw_text = str(result.get('text') or result.get('message') or '')
        existing_think = result.get('think') or result.get('reasoning_content') or ''
        output = dict(result)
    else:
        raw_text = '' if result is None else str(result)
        existing_think = ''
        output = {}

    think, body = _split_think_and_body(raw_text, existing_think)
    text, sources = _rewrite_citations(body, config)
    output.update({
        'think': think,
        'text': text.strip(),
        'sources': sources,
    })
    return output


def _count_user_turns(history: list[dict[str, Any]], current_query: str | None) -> int:
    count = 0
    for msg in history or []:
        if isinstance(msg, dict) and msg.get('role') == 'user':
            content = msg.get('content')
            if isinstance(content, str) and content.strip():
                count += 1
    if current_query and current_query.strip():
        count += 1
    return count


def _count_tool_turns(history: list[dict[str, Any]]) -> int:
    count = 0
    for msg in history or []:
        if (
            isinstance(msg, dict)
            and msg.get('role') == 'assistant'
            and isinstance(msg.get('tool_calls'), list)
            and msg.get('tool_calls')
        ):
            count += 1
    return count
