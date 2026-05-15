from __future__ import annotations

import json
from html import escape
from typing import Any, Optional

_TOOL_PREVIEW_TAG = 'tp'
_TOOL_RESULT_PREVIEW_TAG = 'trp'
_TOOL_CALL_TAG = 'tool_call'
_TOOL_RESULT_TAG = 'tool_result'

_REPRESENTATIVE_TOOL_ARGUMENTS: dict[str, str] = {
    'kb_search': 'query',
    'kb_get_parent_node': 'node_id',
    'kb_get_window_nodes': 'number',
    'kb_keyword_search': 'keyword',
    'web_search': 'query',
    'url_fetch': 'url',
    'arxiv_search': 'query',
    'vision_extractor': 'url',
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
    'web_search': 'query',
    'url_fetch': 'final_url',
    'arxiv_search': 'query',
    'vision_extractor': 'description',
    'skill_manage': 'reason',
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
    'kb_search': 'Checking {value} in the knowledge base for relevant material.',
    'kb_get_parent_node': 'Loading surrounding context for {value} before continuing now.',
    'kb_get_window_nodes': 'Expanding nearby related segments around {value} for review.',
    'kb_keyword_search': 'Searching target documents with {value} as the keyword.',
    'web_search': 'Searching the web for {value}.',
    'url_fetch': 'Reading page content from {value}.',
    'arxiv_search': 'Searching arXiv papers for {value}.',
    'vision_extractor': 'Extracting information from the image.',
    'memory': 'Saving {value} as useful long term memory now.',
    'skill_manage': 'Updating reusable skill notes related to {value} now.',
    'get_skill': 'Opening skill details for {value} before continuing now.',
    'read_reference': 'Reading skill reference material from {value} for review.',
    'run_script': 'Running the selected skill helper script at {value} now.',
    'read_file': 'Reading file content from {value} for review now.',
    'list_dir': 'Listing folder contents from {value} for review now.',
    'search_in_files': 'Searching project files for matches to {value} now.',
    'make_dir': 'Preparing folder {value} for the requested use now.',
    'write_file': 'Writing requested content into file {value} now for update.',
    'delete_file': 'Preparing file {value} for the requested deletion now.',
    'move_file': 'Preparing file move operation starting from {value} now.',
    'download_file': 'Downloading requested file from source {value} now for use.',
}
_TOOL_CALL_FALLBACK_TEMPLATE = 'Preparing the requested tool action for {value}.'

_TOOL_RESULT_PREVIEW_TEMPLATES: dict[str, str] = {
    'kb_search': 'Knowledge base results are ready now.',
    'kb_get_parent_node': 'Surrounding context was loaded successfully now.',
    'kb_get_window_nodes': 'Nearby related segments were expanded successfully.',
    'kb_keyword_search': 'Document keyword results were found successfully.',
    'web_search': 'Web results are ready now.',
    'url_fetch': 'Page content was loaded successfully.',
    'arxiv_search': 'arXiv results are ready now.',
    'vision_extractor': 'Image information has been extracted.',
    'memory': 'Long term memory was saved successfully.',
    'skill_manage': 'Reusable skill notes were updated successfully.',
    'get_skill': 'Skill details were loaded successfully now.',
    'read_reference': 'Skill reference material was loaded successfully.',
    'run_script': 'Skill helper script finished running successfully.',
    'read_file': 'File content was loaded successfully now.',
    'list_dir': 'Folder contents were retrieved successfully now.',
    'search_in_files': 'Project file matches were found successfully.',
    'make_dir': 'Folder is ready for the requested use.',
    'write_file': 'Requested content was written successfully.',
    'delete_file': 'Requested deletion completed successfully now.',
    'move_file': 'Requested file move completed successfully now.',
    'download_file': 'Requested file was downloaded successfully now.',
}

_TOOL_RESULT_FAILURE_TEMPLATES: dict[str, str] = {
    'kb_search': 'Knowledge base results for {value} could not be found.',
    'kb_get_parent_node': 'Surrounding context for {value} could not be loaded.',
    'kb_get_window_nodes': 'Nearby related segments around {value} could not be expanded.',
    'kb_keyword_search': 'Document results for keyword {value} could not be found.',
    'web_search': 'Web results for {value} could not be retrieved.',
    'url_fetch': 'Page content from {value} could not be loaded.',
    'arxiv_search': 'arXiv results for {value} could not be retrieved.',
    'vision_extractor': 'Vision extraction for {value} could not be completed.',
    'memory': 'Long term memory for {value} could not be saved.',
    'skill_manage': 'Reusable skill notes for {value} could not be updated.',
    'get_skill': 'Skill details for {value} could not be loaded.',
    'read_reference': 'Skill reference material from {value} could not be read.',
    'run_script': 'Skill helper script at {value} did not finish.',
    'read_file': 'File content from {value} could not be read.',
    'list_dir': 'Folder contents from {value} could not be listed.',
    'search_in_files': 'Project file search for {value} could not finish.',
    'make_dir': 'Folder {value} could not be prepared for use.',
    'write_file': 'Requested content could not be written into {value} now.',
    'delete_file': 'Requested deletion for file {value} could not complete.',
    'move_file': 'Requested file move from {value} could not complete.',
    'download_file': 'Requested file from {value} could not be downloaded.',
}

_TOOL_RESULT_APPROVAL_TEMPLATES: dict[str, str] = {
    'delete_file': 'Please review the confirmation note "{value}" before deleting this file.',
    'move_file': 'Please review the confirmation note "{value}" before moving this file.',
    'write_file': 'Please review the confirmation note "{value}" before writing this file.',
    'download_file': 'Please review the confirmation note "{value}" before downloading this file.',
}

_TOOL_RESULT_FALLBACK_TEMPLATE = 'Tool results for {value} were received successfully.'
_TOOL_RESULT_FAILURE_FALLBACK_TEMPLATE = 'The step for {value} could not be completed.'
_TOOL_RESULT_APPROVAL_FALLBACK_TEMPLATE = 'Please review the confirmation note "{value}" before continuing.'

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

_FALLBACK_REPRESENTATIVE_ARGUMENT_KEYS = (
    'query',
    'keyword',
    'keywords',
    'url',
    'urls',
    'path',
    'file',
    'filename',
    'rel_path',
    'name',
    'title',
    'topic',
    'pattern',
    'target',
    'node_id',
    'id',
    'src',
    'dst',
    'text',
    'content',
)

_LOW_SIGNAL_ARGUMENT_KEYS = {
    'include_content',
    'include_metadata',
    'include_raw',
    'max_results',
    'limit',
    'top_k',
    'k',
    'page',
    'page_size',
    'offset',
}

_MAX_REPRESENTATIVE_RESULT_LENGTH = 200
_MAX_TOOL_RESULT_PREVIEW_LENGTH = 50

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
    if not isinstance(arguments, dict):
        return arguments
    if key and arguments.get(key) is not None:
        return arguments.get(key)
    return _representative_mapping_value(arguments, _FALLBACK_REPRESENTATIVE_ARGUMENT_KEYS)


def _truncate_representative_result(value: Any) -> str:
    if value is None:
        text = ''
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    else:
        text = str(value)
    if len(text) <= _MAX_REPRESENTATIVE_RESULT_LENGTH:
        return text
    return f'{text[:_MAX_REPRESENTATIVE_RESULT_LENGTH]}...'


def _is_meaningful_preview_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if isinstance(value, bool):
        return False
    return True


def _representative_mapping_value(mapping: dict[str, Any], preferred_keys: tuple[str, ...]) -> Any:
    for key in preferred_keys:
        value = mapping.get(key)
        if _is_meaningful_preview_value(value):
            return value
    for key, value in mapping.items():
        if key in _LOW_SIGNAL_ARGUMENT_KEYS:
            continue
        if _is_meaningful_preview_value(value):
            return value
    return ''


def _friendly_preview_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return ''
    if isinstance(value, dict):
        representative = _representative_mapping_value(
            value,
            _FALLBACK_REPRESENTATIVE_ARGUMENT_KEYS + _FALLBACK_REPRESENTATIVE_RESULT_KEYS,
        )
        if representative is value or not _is_meaningful_preview_value(representative):
            return 'the selected options'
        return _friendly_preview_text(representative)
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if not items:
            return ''
        friendly_items = [
            _friendly_preview_text(item)
            for item in items[:2]
            if _is_meaningful_preview_value(item)
        ]
        friendly_items = [item for item in friendly_items if item]
        if friendly_items:
            preview = ', '.join(friendly_items)
            if len(items) > 2:
                return f'{preview} and {len(items) - 2} more'
            return preview
        return f'{len(items)} items'
    return str(value)


def _representative_tool_result(tool_name: str, result: Any) -> Any:
    if isinstance(result, dict):
        key = _REPRESENTATIVE_TOOL_RESULTS.get(tool_name)
        if key and result.get(key) is not None:
            return result.get(key)
        for fallback_key in _FALLBACK_REPRESENTATIVE_RESULT_KEYS:
            if result.get(fallback_key) is not None:
                return result.get(fallback_key)
        if result:
            first_key = next(iter(result))
            return result.get(first_key)
        return ''
    if isinstance(result, list):
        return result
    return result


def _tool_call_id(tool_call: dict[str, Any], round_index: int, ordinal: int) -> str:
    tool_call_id = str(tool_call.get('id') or '').strip()
    if tool_call_id:
        return tool_call_id
    return f'toolcall-{round_index}-{ordinal}'


def _tool_preview_value(value: Any) -> str:
    text = _truncate_representative_result(_friendly_preview_text(value))
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
    template = template_map.get(tool_name) or fallback_template
    if '{value}' not in template:
        return template
    preview_value = value or 'the current item'
    return template.format(value=f'**{preview_value}**')


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
    if isinstance(result, dict) and result.get('total') == 0 and tool_name.startswith('kb_'):
        if tool_name == 'kb_search':
            return 'Knowledge base search finished with no matching results'
        if tool_name == 'kb_get_parent_node':
            return 'No parent context was found for the requested node'
        if tool_name == 'kb_get_window_nodes':
            return 'No nearby knowledge base segments were found'
        if tool_name == 'kb_keyword_search':
            return 'Keyword search finished with no matching document segments'
    return _render_preview_template(
        tool_name,
        _truncate_tool_result_preview(_representative_tool_result(tool_name, result)),
        _TOOL_RESULT_PREVIEW_TEMPLATES,
        _TOOL_RESULT_FALLBACK_TEMPLATE,
    )


def _tool_call_frame_text(tool_call: dict[str, Any]) -> str:
    tool_call_id = str(tool_call.get('id') or '')
    tool_name = str(tool_call.get('name', ''))
    arguments = tool_call.get('arguments', {})
    payload = {
        'id': tool_call_id,
        'name': tool_name,
        'arguments': arguments if isinstance(arguments, dict) else {},
    }
    preview = _tool_call_preview(tool_name, arguments)
    return (
        f'<{_TOOL_PREVIEW_TAG} id="{escape(tool_call_id, quote=True)}">{preview}</{_TOOL_PREVIEW_TAG}>'
        f'<{_TOOL_CALL_TAG}>{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}</{_TOOL_CALL_TAG}>'
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
    preview = _tool_result_preview(tool_name, result)
    return (
        f'<{_TOOL_RESULT_PREVIEW_TAG} id="{escape(tool_call_id, quote=True)}">{preview}</{_TOOL_RESULT_PREVIEW_TAG}>'
        f'<{_TOOL_RESULT_TAG}>{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}</{_TOOL_RESULT_TAG}>'
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
    if '![' in text:
        yield text
        return
    chunk_size = max(1, int(chunk_size or _STREAM_CHUNK_SIZE))
    for start in range(0, len(text), chunk_size):
        yield text[start:start + chunk_size]
