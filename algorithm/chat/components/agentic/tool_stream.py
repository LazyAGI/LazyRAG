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
    'kb_search': '正在知识库中查找{value}相关资料',
    'kb_get_parent_node': '正在补充上下文信息',
    'kb_get_window_nodes': '正在展开相关片段',
    'kb_keyword_search': '正在按关键词在目标文档中查找资料',
    'memory': '正在记录这条记忆',
    'skill_manage': '正在整理可复用的技能',
    'get_skill': '正在查看技能的详细内容',
    'read_reference': '正在查看技能参考资料',
    'run_script': '正在运行技能的辅助脚本',
    'read_file': '正在查看文件内容',
    'list_dir': '正在查看文件夹内容',
    'search_in_files': '正在查找相关内容',
    'make_dir': '正在准备文件夹',
    'write_file': '正在写入文件',
    'delete_file': '正在删除文件',
    'move_file': '正在整理文件位置',
    'download_file': '正在下载所需文件',
}
_TOOL_CALL_FALLBACK_TEMPLATE = '正在处理请求'

_TOOL_RESULT_PREVIEW_TEMPLATES: dict[str, str] = {
    'kb_search': '已找到{value}个相关资料',
    'kb_get_parent_node': '已补充上文信息',
    'kb_get_window_nodes': '已展开相关片段',
    'kb_keyword_search': '已找到关键词相关资料',
    'memory': '已记录这条记忆',
    'skill_manage': '已整理可复用技能',
    'get_skill': '已读取技能的详细内容',
    'read_reference': '已读取技能参考资料',
    'run_script': '技能辅助脚本已运行完成',
    'read_file': '已读取文件内容',
    'list_dir': '已获取文件夹内容',
    'search_in_files': '已完成内容查找',
    'make_dir': '已准备文件夹',
    'write_file': '已写入文件',
    'delete_file': '已删除文件',
    'move_file': '已更新文件位置',
    'download_file': '已下载所需文件',
}

_TOOL_RESULT_FAILURE_TEMPLATES: dict[str, str] = {
    'kb_search': '没能找到相关资料',
    'kb_get_parent_node': '没能补充上文信息',
    'kb_get_window_nodes': '没能展开相关片段',
    'kb_keyword_search': '没能按关键词找到资料',
    'memory': '没能记录这条记忆',
    'skill_manage': '没能整理可复用技能',
    'get_skill': '获取技能详细信息失败',
    'read_reference': '没能读取参考资料',
    'run_script': '辅助脚本没能运行完成',
    'read_file': '没能读取文件内容',
    'list_dir': '没能获取文件夹内容',
    'search_in_files': '没能完成内容查找',
    'make_dir': '没能准备好文件夹',
    'write_file': '没能写入文件',
    'delete_file': '没能删除文件',
    'move_file': '没能整理文件位置',
    'download_file': '没能下载所需文件',
}

_TOOL_RESULT_APPROVAL_TEMPLATES: dict[str, str] = {
    'delete_file': '删除文件前还需要进一步确认',
    'move_file': '调整文件位置前还需要进一步确认',
    'write_file': '写入文件前还需要进一步确认',
    'download_file': '下载文件前还需要进一步确认',
}

_TOOL_RESULT_FALLBACK_TEMPLATE = '已获得处理结果'
_TOOL_RESULT_FAILURE_FALLBACK_TEMPLATE = '暂时没能完成这一步'
_TOOL_RESULT_APPROVAL_FALLBACK_TEMPLATE = '这一步还需要进一步确认'

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
