from __future__ import annotations

import json
from html import escape
from typing import Any, Optional

_REPRESENTATIVE_TOOL_ARGUMENTS: dict[str, str] = {
    'kb_search': 'query',
    'kb_get_parent_node': 'node_id',
    'kb_get_window_nodes': 'number',
    'kb_keyword_search': 'keyword',
    'memory': 'target',
    'skill_manage': 'name',
    'get_skill': 'name',
    'read_reference': 'rel_path',
    'run_script': 'rel_path',
    'read_file': 'path',
    'list_dir': 'path',
    'search_in_files': 'pattern',
    'make_dir': 'path',
    'write_file': 'path',
    'delete_file': 'path',
    'move_file': 'src',
    'download_file': 'url',
}

_REPRESENTATIVE_TOOL_RESULTS: dict[str, str] = {
    'skill_manage': 'reason',
    'get_skill': 'content',
    'read_reference': 'content',
    'run_script': 'stdout',
    'read_file': 'content',
    'list_dir': 'path',
    'search_in_files': 'status',
    'make_dir': 'path',
    'write_file': 'path',
    'delete_file': 'path',
    'move_file': 'dst',
    'download_file': 'path',
}

_TOOL_CALL_PREVIEW_TEMPLATES: dict[str, str] = {
    'kb_search': 'Searching knowledge base for {value}-related content',
    'kb_get_parent_node': 'Fetching context information',
    'kb_get_window_nodes': 'Expanding related segments',
    'kb_keyword_search': 'Searching target documents by keyword',
    'memory': 'Recording this memory',
    'skill_manage': 'Organizing reusable skills',
    'get_skill': 'Reading skill details',
    'read_reference': 'Reading skill reference material',
    'run_script': 'Running skill helper script',
    'read_file': 'Reading file content',
    'list_dir': 'Listing directory content',
    'search_in_files': 'Searching for relevant content',
    'make_dir': 'Preparing directory',
    'write_file': 'Writing file',
    'delete_file': 'Deleting file',
    'move_file': 'Moving file',
    'download_file': 'Downloading file',
}
_TOOL_CALL_FALLBACK_TEMPLATE = 'Processing request'

_TOOL_RESULT_PREVIEW_TEMPLATES: dict[str, str] = {
    'kb_search': 'Found {value} relevant results',
    'kb_get_parent_node': 'Context information fetched',
    'kb_get_window_nodes': 'Related segments expanded',
    'kb_keyword_search': 'Found keyword-related results',
    'memory': 'Memory recorded',
    'skill_manage': 'Reusable skills organized',
    'get_skill': 'Skill details loaded',
    'read_reference': 'Skill reference material loaded',
    'run_script': 'Skill helper script completed',
    'read_file': 'File content loaded',
    'list_dir': 'Directory content retrieved',
    'search_in_files': 'Content search completed',
    'make_dir': 'Directory prepared',
    'write_file': 'File written',
    'delete_file': 'File deleted',
    'move_file': 'File moved',
    'download_file': 'File downloaded',
}

_TOOL_RESULT_FAILURE_TEMPLATES: dict[str, str] = {
    'kb_search': 'Could not find relevant results',
    'kb_get_parent_node': 'Could not fetch context information',
    'kb_get_window_nodes': 'Could not expand related segments',
    'kb_keyword_search': 'Could not find keyword-related results',
    'memory': 'Could not record this memory',
    'skill_manage': 'Could not organize reusable skills',
    'get_skill': 'Failed to retrieve skill details',
    'read_reference': 'Could not read reference material',
    'run_script': 'Helper script did not complete',
    'read_file': 'Could not read file content',
    'list_dir': 'Could not retrieve directory content',
    'search_in_files': 'Content search did not complete',
    'make_dir': 'Could not prepare directory',
    'write_file': 'Could not write file',
    'delete_file': 'Could not delete file',
    'move_file': 'Could not move file',
    'download_file': 'Could not download file',
}

_TOOL_RESULT_APPROVAL_TEMPLATES: dict[str, str] = {
    'delete_file': 'Confirmation required before deleting file',
    'move_file': 'Confirmation required before moving file',
    'write_file': 'Confirmation required before writing file',
    'download_file': 'Confirmation required before downloading file',
}

_TOOL_RESULT_FALLBACK_TEMPLATE = 'Result received'
_TOOL_RESULT_FAILURE_FALLBACK_TEMPLATE = 'Could not complete this step'
_TOOL_RESULT_APPROVAL_FALLBACK_TEMPLATE = 'This step requires further confirmation'

_FALLBACK_REPRESENTATIVE_RESULT_KEYS = (
    'result',
    'content',
    'text',
    'reason',
    'message',
    'stdout',
    'stderr',
    'status',
    'path',
)

_MAX_REPRESENTATIVE_RESULT_LENGTH = 200
_MAX_TOOL_RESULT_PREVIEW_LENGTH = 50

_TOOL_CALL_TAG = 'tool_call'
_TOOL_RESULT_TAG = 'tool_result'
_TOOL_PREVIEW_TAG = 'tp'
_TOOL_RESULT_PREVIEW_TAG = 'trp'
_STREAM_CHUNK_SIZE = 24


def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get('function') or {}
    arguments = function.get('arguments', {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            pass
    return {
        'id': tool_call.get('id', ''),
        'name': function.get('name', ''),
        'arguments': arguments,
    }


def _representative_tool_argument(tool_name: str, arguments: Any) -> Any:
    key = _REPRESENTATIVE_TOOL_ARGUMENTS.get(tool_name)
    if not key or not isinstance(arguments, dict):
        return arguments
    return arguments.get(key, '')


def _truncate_representative_result(value: Any) -> str:
    text = '' if value is None else str(value)
    if len(text) <= _MAX_REPRESENTATIVE_RESULT_LENGTH:
        return text
    return f'{text[:_MAX_REPRESENTATIVE_RESULT_LENGTH]}...'


def _representative_tool_result(tool_name: str, result: Any) -> str:
    if isinstance(result, dict):
        key = _REPRESENTATIVE_TOOL_RESULTS.get(tool_name)
        if key and result.get(key) is not None:
            return _truncate_representative_result(result.get(key))
        for fallback_key in _FALLBACK_REPRESENTATIVE_RESULT_KEYS:
            if result.get(fallback_key) is not None:
                return _truncate_representative_result(result.get(fallback_key))
        if result:
            first_key = next(iter(result))
            return _truncate_representative_result(result.get(first_key))
        return ''
    if isinstance(result, list):
        if not result:
            return ''
        first_item = result[0]
        if len(result) > 1:
            return _truncate_representative_result(f'{first_item} ... ({len(result)} items)')
        return _truncate_representative_result(first_item)
    return _truncate_representative_result(result)


def _tool_payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def _tool_call_id(tool_call: dict[str, Any], round_index: int, ordinal: int) -> str:
    tool_call_id = str(tool_call.get('id') or '').strip()
    if tool_call_id:
        return tool_call_id
    return f'toolcall-{round_index}-{ordinal}'


def _tool_preview_value(value: Any) -> str:
    text = _truncate_representative_result(value)
    return text.replace('\n', ' ').strip()


def _truncate_tool_result_preview(value: Any) -> str:
    text = _tool_preview_value(value)
    if len(text) <= _MAX_TOOL_RESULT_PREVIEW_LENGTH:
        return text
    return f'{text[:_MAX_TOOL_RESULT_PREVIEW_LENGTH]}...'


def _tool_result_status(result: Any) -> str:
    if isinstance(result, dict):
        success = result.get('success')
        if success is False:
            return 'failed'
        status = str(result.get('status') or '').strip().lower()
        if status == 'needs_approval':
            return 'needs_approval'
        if status in ('error', 'missing', 'failed', 'fail'):
            return 'failed'
    return 'ok'


def _tool_result_failure_detail(result: Any) -> str:
    if isinstance(result, dict):
        for key in ('reason', 'error', 'message', 'path', 'status'):
            value = result.get(key)
            if value:
                return _truncate_tool_result_preview(value)
    return _truncate_tool_result_preview(result)


def _render_preview_template(
    tool_name: str,
    value: str,
    template_map: dict[str, str],
    fallback_template: str,
) -> str:
    template = template_map.get(tool_name)
    if template:
        if '{value}' not in template:
            return template
        if value:
            return template.format(value=value)
        return template.replace('：{value}', '').replace('{value}', '')
    return fallback_template


def _tool_call_preview(tool_name: str, arguments: Any) -> str:
    representative_argument = _representative_tool_argument(tool_name, arguments)
    preview = _tool_preview_value(representative_argument)
    return _render_preview_template(
        tool_name,
        preview,
        _TOOL_CALL_PREVIEW_TEMPLATES,
        _TOOL_CALL_FALLBACK_TEMPLATE,
    )


def _tool_result_preview(tool_name: str, result: Any) -> str:
    status = _tool_result_status(result)
    if status == 'needs_approval':
        return _render_preview_template(
            tool_name,
            _tool_result_failure_detail(result),
            _TOOL_RESULT_APPROVAL_TEMPLATES,
            _TOOL_RESULT_APPROVAL_FALLBACK_TEMPLATE,
        )
    if status == 'failed':
        return _render_preview_template(
            tool_name,
            _tool_result_failure_detail(result),
            _TOOL_RESULT_FAILURE_TEMPLATES,
            _TOOL_RESULT_FAILURE_FALLBACK_TEMPLATE,
        )
    return _render_preview_template(
        tool_name,
        _truncate_tool_result_preview(_representative_tool_result(tool_name, result)),
        _TOOL_RESULT_PREVIEW_TEMPLATES,
        _TOOL_RESULT_FALLBACK_TEMPLATE,
    )


def _tagged_tool_frame(payload_tag: str, payload: dict[str, Any]) -> str:
    return f'<{payload_tag}>{_tool_payload_json(payload)}</{payload_tag}>'


def _tagged_preview_frame(preview_tag: str, tool_call_id: str, preview: str) -> str:
    return f'<{preview_tag} id="{escape(tool_call_id, quote=True)}">{escape(preview)}</{preview_tag}>'


def _tool_call_frame_text(tool_call: dict[str, Any]) -> str:
    tool_call_id = str(tool_call.get('id') or '')
    tool_name = str(tool_call.get('name', ''))
    arguments = tool_call.get('arguments', {})
    payload = {
        'id': tool_call_id,
        'name': tool_name,
        'arguments': arguments,
    }
    return (
        _tagged_preview_frame(
            _TOOL_PREVIEW_TAG,
            tool_call_id,
            _tool_call_preview(tool_name, arguments),
        )
        + _tagged_tool_frame(_TOOL_CALL_TAG, payload)
    )


def _tool_result_frame_text(tool_result: dict[str, Any]) -> str:
    tool_call_id = str(tool_result.get('id') or '')
    tool_name = str(tool_result.get('tool_name', ''))
    result = tool_result.get('result')
    payload = {
        'id': tool_call_id,
        'name': tool_name,
        'result': result,
    }
    return (
        _tagged_preview_frame(
            _TOOL_RESULT_PREVIEW_TAG,
            tool_call_id,
            _tool_result_preview(tool_name, result),
        )
        + _tagged_tool_frame(_TOOL_RESULT_TAG, payload)
    )


def _stream_frame(
    *,
    think: Optional[str] = None,
    text: Optional[str] = None,
    sources: Optional[list[dict[str, Any]]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    frame = {
        'think': think,
        'text': text,
        'sources': sources or [],
    }
    if extra:
        frame.update(extra)
    return frame


def _format_tool_stream_frame(tool_event: dict[str, Any]) -> Optional[dict[str, Any]]:
    tool_calls = tool_event.get('tool_calls') or []
    tool_results = tool_event.get('tool_results') or []
    if not tool_calls and not tool_results:
        return None

    frame_parts: list[str] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            frame_parts.append(_tool_call_frame_text(tool_call))
    for tool_result in tool_results:
        if isinstance(tool_result, dict):
            frame_parts.append(_tool_result_frame_text(tool_result))
    return _stream_frame(text=''.join(frame_parts))


def _iter_text_chunks(text: str, chunk_size: int = _STREAM_CHUNK_SIZE):
    if not text:
        return
    chunk_size = max(1, int(chunk_size or _STREAM_CHUNK_SIZE))
    for start in range(0, len(text), chunk_size):
        yield text[start:start + chunk_size]
