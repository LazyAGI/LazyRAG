from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from termios import FLUSHO
import threading
import time
import traceback
from collections import OrderedDict
from functools import lru_cache
from html import escape
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Optional, Tuple

import lazyllm
from lazyllm import loop, once_wrapper
from lazyllm.tools.agent.functionCall import FunctionCall
from lazyllm.tools.sandbox.sandbox_base import create_sandbox
from lazyllm.tools.fs.client import FS

base_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(base_dir))

from chat.pipelines.builders.get_models import get_automodel
from chat.tools.skill_manager import list_all_skills_with_category
from chat.utils.load_config import load_model_config
from chat.prompts.agentic_v2 import (
    DEFAULT_SYSTEM_PROMPT,
    MEMORY_GUIDANCE,
    SKILLS_GUIDANCE,
    TOOL_CALL_STATUS_GUIDANCE,
    TOOL_USE_ENFORCEMENT_GUIDANCE,
    _SKILL_REVIEW_PROMPT,
    _MEMORY_REVIEW_PROMPT,
    _COMBINED_REVIEW_PROMPT,
    _MEMORY_FLUSH_MESSAGES,
)


ALL_TOOLS = [
    'kb_search',
    'kb_get_parent_node',
    'kb_get_window_nodes',
    'kb_keyword_search',
    'memory',
    'skill_manage',
]

AVAILABLE_TOOLS = [
    'kb_search',
    'kb_get_parent_node',
    'kb_get_window_nodes',
    'kb_keyword_search',
    'memory',
    'skill_manage',
]

CITATION_GUIDANCE = '''# Citation Rules
When using evidence returned by knowledge-base tools, cite it with the exact `ref` marker from the tool result, such as `[[1]]`.
Put the citation immediately after the supported sentence or paragraph.
Do not invent citation numbers. Do not rewrite `[[n]]` into links yourself.
使用知识库工具返回的证据作答时，必须使用工具结果中的原始 `ref` 标记（如 `[[1]]`）作为引用。
引用应紧跟被该证据支持的句子或段落；不要自造编号，也不要自己把 `[[n]]` 改写成链接。'''

_CITATION_REFS_KEY = '_citation_sources'
_CITATION_KEY_MAP_KEY = '_citation_key_map'
_CITATION_NEXT_KEY = '_citation_next_index'
_CITATION_PATTERN = re.compile(r'\[\[(\d+)\]\]')
_THINK_BLOCK_PATTERN = re.compile(r'<think>(.*?)</think>', re.DOTALL)
_STREAM_CHUNK_SIZE = 24
_FINISH_REASON_UNSPECIFIED = 'FINISH_REASON_UNSPECIFIED'
_FINISH_REASON_STOP = 'FINISH_REASON_STOP'

_REVIEW_TOOLS: dict[str, list[str]] = {
    'memory':   ['memory'],
    'skill':    ['skill_manage'],
    'combined': ['memory', 'skill_manage'],
}

_REVIEW_PROMPTS: dict[str, str] = {
    'memory':   _MEMORY_REVIEW_PROMPT,
    'skill':    _SKILL_REVIEW_PROMPT,
    'combined': _COMBINED_REVIEW_PROMPT,
}

_REPRESENTATIVE_TOOL_ARGUMENTS: dict[str, str] = {
    'kb_search': 'query',
    'kb_get_parent_node': 'node_id',
    'kb_get_window_nodes': 'number',
    'kb_keyword_search': 'keyword',
    'memory': 'target',
    'skill_manage': 'name',
}


def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get('function') or {}
    arguments = function.get('arguments', {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            pass
    return {
        'name': function.get('name', ''),
        'arguments': arguments,
    }


def _representative_tool_argument(tool_name: str, arguments: Any) -> Any:
    key = _REPRESENTATIVE_TOOL_ARGUMENTS.get(tool_name)
    if not key or not isinstance(arguments, dict):
        return arguments
    return arguments.get(key, '')


class _StreamingFunctionCall(FunctionCall):
    def __init__(self, *args: Any, stream_event_callback=None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._stream_event_callback = stream_event_callback
        self._round_index = 0

    def _post_action(self, llm_output: Dict[str, Any]):
        self._round_index += 1
        if (
            isinstance(llm_output, dict)
            and not llm_output.get('tool_calls')
            and isinstance(llm_output.get('content'), str)
        ):
            match = re.search(
                r'Action:\s*Call\s+(\w+)\s+with\s+parameters\s+(\{.*?\})',
                llm_output['content'],
            )
            if match:
                try:
                    llm_output['tool_calls'] = [{
                        'function': {
                            'name': match.group(1),
                            'arguments': json.loads(match.group(2)),
                        },
                    }]
                except json.JSONDecodeError:
                    pass
        if self._stream_event_callback and isinstance(llm_output, dict):
            tool_calls = llm_output.get('tool_calls') or []
            self._stream_event_callback({
                'round': self._round_index,
                'content': llm_output.get('content', ''),
                'tool_calls': [
                    _normalize_tool_call(tc)
                    for tc in tool_calls
                    if isinstance(tc, dict)
                ],
            })
        return super()._post_action(llm_output)


class _StreamingReactAgent(lazyllm.tools.agent.ReactAgent):
    def __init__(self, *args: Any, stream_event_callback=None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._stream_event_callback = stream_event_callback

    @once_wrapper(reset_on_pickle=True)
    def build_agent(self):
        agent = loop(
            _StreamingFunctionCall(
                llm=self._llm,
                _prompt=self._prompt,
                return_trace=self._return_trace,
                stream=self._stream,
                _tool_manager=self._tools_manager,
                skill_manager=self._skill_manager,
                workspace=self.workspace,
                keep_full_turns=self._keep_full_turns,
                stream_event_callback=self._stream_event_callback,
            ),
            stop_condition=lambda x: isinstance(x, str),
            count=20,
        )
        self._agent = agent


def _normalize_available_tools(tools: Any) -> list[str]:
    if tools is None:
        return list(AVAILABLE_TOOLS)
    if isinstance(tools, str):
        tools = [tools]
    if not isinstance(tools, list):
        return list(AVAILABLE_TOOLS)
    if any(isinstance(t, str) and t.lower() == 'all' for t in tools):
        return list(ALL_TOOLS)
    return [t for t in tools if isinstance(t, str) and t]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == '':
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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
        'available_tools': AVAILABLE_TOOLS,
        'skill_fs_local_base_dir': '.agentic_rag/skills',
        'memory_fs_dir': '.agentic_rag/memory',
        'core_api_url': os.getenv('LAZYRAG_CORE_API_URL', 'http://core:8000'),
        'workspace': './workspace',
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

    return '\n\n'.join(prompt_parts)


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
    collected: 'OrderedDict[int, dict[str, Any]]' = OrderedDict()

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
    if not tool_calls:
        return None

    _, visible_content = _split_think_and_body(str(tool_event.get('content') or ''))
    tools = [
        {
            'name': tool_call.get('name', ''),
            'argument': _representative_tool_argument(
                tool_call.get('name', ''),
                tool_call.get('arguments', {}),
            ),
        }
        for tool_call in tool_calls
        if isinstance(tool_call, dict)
    ]
    return _stream_frame(
        think=visible_content.strip(),
        extra={'tools': tools},
    )


def _iter_text_chunks(text: str, chunk_size: int = _STREAM_CHUNK_SIZE):
    if not text:
        return
    chunk_size = max(1, int(chunk_size or _STREAM_CHUNK_SIZE))
    for start in range(0, len(text), chunk_size):
        yield text[start:start + chunk_size]


def _count_user_turns(history: list[dict[str, Any]], current_query: str | None) -> int:
    """Count how many user turns have happened up to and including the current one."""
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
    """Count assistant turns that contain at least one tool call."""
    count = 0
    for msg in history or []:
        if isinstance(msg, dict) and msg.get('role') != 'tool':
            count += 1
    return count


def _decide_review_mode(
    available_tools: list[str],
    tool_turns: int,
    user_turns: int,
    memory_review_interval: int,
    skill_review_interval: int,
) -> str | None:
    """Decide which background review (if any) to spawn after this turn."""
    if os.getenv('LAZYRAG_SKILL_REVIEW_DEBUG', '').lower() in ('1', 'true', 'yes'):
        return 'combined'

    memory_due = (
        'memory' in available_tools
        and user_turns > memory_review_interval
    )
    skill_due = (
        'skill_manage' in available_tools
        and tool_turns > skill_review_interval
        and user_turns > 1
    )
    if memory_due and skill_due:
        return 'combined'
    if memory_due:
        return 'memory'
    if skill_due:
        return 'skill'
    return None


def _spawn_background_review(
    config: dict,
    llm: Any,
    sandbox: Any,
    keep_full_turns: int,
    history_snapshot: list,
    review_mode: str,
    request_global_sid: str,
) -> None:
    review_tools = _REVIEW_TOOLS.get(review_mode, [])
    review_prompt = _REVIEW_PROMPTS.get(review_mode, _COMBINED_REVIEW_PROMPT)
    if not review_tools:
        return

    snapshot = list(history_snapshot)
    # Only skill / combined reviews need the skill catalogue; memory-only
    # review has no use for it.
    review_skills = (
        list_all_skills_with_category(config.get('skill_fs_local_base_dir'))
        if review_mode in ('skill', 'combined')
        else []
    )

    def _worker() -> None:
        tname = threading.current_thread().name
        print(f'[bg-review:{review_mode}] START thread={tname} sid={request_global_sid}')
        try:
            # Keep session-level global config shared with main react.
            lazyllm.globals._init_sid(request_global_sid)
            # Isolate per-react runtime state (_lazyllm_agent, bind_args, ...).
            lazyllm.locals._init_sid()
            lazyllm.globals['agentic_config'] = config

            review_agent = lazyllm.tools.agent.ReactAgent(
                llm=llm,
                tools=review_tools,
                max_retries=_env_int('LAZYRAG_REVIEW_MAX_RETRIES', 5),
                return_trace=False,
                prompt=review_prompt,
                skills=list(review_skills.keys()),
                keep_full_turns=keep_full_turns,
                sandbox=sandbox,
                fs=FS,
                skills_dir=config['skill_fs_local_base_dir'],
                enable_builtin_tools=False,
                force_summarize=True,
                force_summarize_context=review_prompt,
            )
            res = review_agent(_MEMORY_FLUSH_MESSAGES['session_end'], llm_chat_history=snapshot)
            print(f'[bg-review:{review_mode}] DONE thread={tname}\n{res}')
        except Exception:
            print(f'[bg-review:{review_mode}] FAILED thread={tname}')
            traceback.print_exc()
        finally:
            lazyllm.locals.clear()
            print(f'[bg-review:{review_mode}] EXIT thread={tname}')

    if os.getenv('LAZYRAG_REVIEW_DEBUG', '').lower() in ('1', 'true', 'yes'):
        _worker()
    else:
        thread = threading.Thread(target=_worker, daemon=True)
        print(f'[bg-review:{review_mode}] spawn sid={request_global_sid}')
        thread.start()


def agentic_forward(
    query: str,
    history: list[dict[str, Any]],
    stream_event_callback=None,
) -> Any:
    config = lazyllm.globals.get('agentic_config') or {}
    if not isinstance(config, dict):
        config = {}
    config = _with_agentic_defaults(config)

    llm = get_automodel('llm')
    sandbox = create_sandbox(project_dir=str(base_dir))
    available_skills = list_all_skills_with_category(config.get('skill_fs_local_base_dir'))
    available_tools = _filter_tools_for_request(
        _normalize_available_tools(config.get('available_tools')),
        config,
    )
    config['available_tools'] = available_tools

    keep_full_turns = config.get('keep_full_turns', 3)
    runtime_prompt = _build_runtime_system_prompt(config, available_tools)
    agent_cls = _StreamingReactAgent if stream_event_callback else lazyllm.tools.agent.ReactAgent
    agent_kwargs = {
        'llm': llm,
        'tools': available_tools,
        'max_retries': _env_int('LAZYRAG_MAX_RETRIES', 20),
        'return_trace': config.get('return_trace', False),
        'prompt': runtime_prompt,
        'skills': list(available_skills.keys()),
        'workspace': config.get('workspace', './workspace'),
        'keep_full_turns': keep_full_turns,
        'sandbox': sandbox,
        'fs': FS,
        'skills_dir': config['skill_fs_local_base_dir'],
        'enable_builtin_tools': False,
        'force_summarize': True,
        'force_summarize_context': query,
    }
    if stream_event_callback:
        agent_kwargs['stream_event_callback'] = stream_event_callback

    react_agent = agent_cls(
        **agent_kwargs,
    )

    request_global_sid = lazyllm.globals._sid
    lazyllm.globals['agentic_config'] = config
    agent_output = react_agent(query, llm_chat_history=history)
    agent_history = lazyllm.locals.get('_lazyllm_agent', {}).get('history', [])
    history_snapshot = agent_history
    if runtime_prompt and (not history_snapshot or history_snapshot[0].get('role') != 'system'):
        history_snapshot = [{'role': 'system', 'content': runtime_prompt}] + history_snapshot + [{'role': 'assistant', 'content': agent_output}]
    tool_turns = _count_tool_turns(agent_history)
    user_turns = _count_user_turns(history, query)
    review_mode = _decide_review_mode(
        available_tools=available_tools,
        tool_turns=tool_turns,
        user_turns=user_turns,
        memory_review_interval=_env_int('LAZYRAG_MEMORY_REVIEW_INTERVAL', 1),
        skill_review_interval=_env_int('LAZYRAG_SKILL_REVIEW_INTERVAL', 5),
    )
    if review_mode is not None:
        _spawn_background_review(
            config=config,
            llm=llm,
            sandbox=sandbox,
            keep_full_turns=keep_full_turns,
            history_snapshot=history_snapshot,
            review_mode=review_mode,
            request_global_sid=request_global_sid,
        )

    return agent_output


async def _agentic_forward_stream(
    query: str,
    history: list[dict[str, Any]],
    runtime_params: dict[str, Any],
    global_sid: str,
    local_sid: str,
):
    event_queue: Queue = Queue()
    sentinel = object()
    closed = threading.Event()
    started_at = time.time()

    def _emit_event(event: dict[str, Any]) -> None:
        if not closed.is_set():
            event_queue.put({'type': 'tool_event', 'event': event})

    def _worker() -> None:
        lazyllm.globals._init_sid(global_sid)
        lazyllm.locals._init_sid(local_sid)
        lazyllm.globals['agentic_config'] = runtime_params
        try:
            result = agentic_forward(
                query=query,
                history=history,
                stream_event_callback=_emit_event,
            )
            if not closed.is_set():
                event_queue.put({'type': 'final', 'result': result})
        except Exception as exc:
            if not closed.is_set():
                event_queue.put(exc)
        finally:
            if not closed.is_set():
                event_queue.put(sentinel)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    final_result = None
    try:
        while True:
            event = await asyncio.to_thread(event_queue.get)
            if event is sentinel:
                break
            if isinstance(event, Exception):
                raise event
            if isinstance(event, dict) and event.get('type') == 'final':
                final_result = event.get('result')
            elif isinstance(event, dict) and event.get('type') == 'tool_event':
                tool_event = event.get('event') or {}
                frame = _format_tool_stream_frame(tool_event)
                if frame is None:
                    continue
                yield frame

        elapsed_s = int(time.time() - started_at)
        output = _format_non_stream_result(final_result, runtime_params)
        chunk_size = int(runtime_params.get('stream_chunk_size') or _STREAM_CHUNK_SIZE)
        for chunk in _iter_text_chunks(str(output.get('think') or ''), chunk_size):
            yield _stream_frame(
                think=chunk,
            )

        for chunk in _iter_text_chunks(str(output.get('text') or ''), chunk_size):
            yield _stream_frame(
                text=chunk,
            )

        sources = output.get('sources') or []
        if sources:
            yield _stream_frame(
                text='',
                sources=sources,
            )
    finally:
        closed.set()
        worker.join(timeout=0)


def _ensure_tools_registered() -> None:
    # Trigger @fc_register side effects once so ReactAgent can resolve tool names.
    from chat.tools import kb, memory, skill_manager  # noqa: F401


def _parse_dataset_url(dataset_url: str) -> Tuple[str, str]:
    parts = [p.strip() for p in str(dataset_url).split(',', 1)]
    kb_url = parts[0] if parts else ''
    kb_id = parts[1] if len(parts) > 1 else ''
    return kb_url, kb_id


@lru_cache(maxsize=1)
def _get_cwd() -> str:
    return str(Path.cwd())


@lru_cache(maxsize=1)
def _get_runtime_agent_defaults() -> Dict[str, Any]:
    config = load_model_config()
    defaults = config.get('agentic_v2', {})
    return dict(defaults) if isinstance(defaults, dict) else {}


def agentic_rag_v2(
    global_params: Dict[str, Any],
    tool_params: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    **kwargs: Any,
) -> Any:
    _ensure_tools_registered()

    query = (global_params or {}).get('query', '')
    if not isinstance(query, str) or not query.strip():
        raise ValueError('query is required')

    history = (global_params or {}).get('history') or []
    if not isinstance(history, list):
        history = []

    runtime_params = _get_runtime_agent_defaults()
    runtime_params.update(global_params or {})
    runtime_params.update(kwargs)
    runtime_params['stream'] = stream
    runtime_params = _with_agentic_defaults(runtime_params)
    _sync_request_context(runtime_params)
    _reset_citation_state(runtime_params)

    lazyllm.globals['agentic_config'] = runtime_params

    if not stream:
        result = agentic_forward(query=query.strip(), history=history)
        return _format_non_stream_result(result, runtime_params)

    return _agentic_forward_stream(
        query=query.strip(),
        history=history,
        runtime_params=runtime_params,
        global_sid=lazyllm.globals._sid,
        local_sid=lazyllm.locals._sid,
    )


if __name__ == '__main__':
    # Import tool modules so their @fc_register decorators run and register
    # the tools into lazyllm's function-call registry before ReactAgent is built.
    from chat.tools import kb, memory, skill_manager  # noqa: F401

    agentic_config = {
        # 'kb_url': 'http://10.119.16.66:9010',
        # 'kb_name': 'tyy_recall_0319_a',
        # 'kb_id': 'ds_9e96150bb1ceeec7d96055638072b8a9',
        'kb_url': 'http://10.119.24.129:8056',
        'kb_name': 'general_algo',
        'kb_id': 'ds_9e96150bb1ceeec7d96055638072b8a9',
        'es_url': 'https://10.119.24.129:9200',
        'es_index': 'tyy_recall_0319_a',
        'es_user': 'admin',
        'es_password': 'LazyRAG_OpenSearch123!',
        'available_tools': AVAILABLE_TOOLS,
        'skill_fs_local_base_dir': '.agentic_rag/skills',
        'memory_fs_dir': '.agentic_rag/memory',
        'core_api_url': 'http://10.119.24.129:9090',
        'workspace': '/tmp/test_agentic_workspace',
    }

    lazyllm.globals['agentic_config'] = agentic_config

    # query = '我是铁路工程师，需要根据法规判断下面这句话是不是正确。白沈家沟特大桥、浪加河特大桥泥岩夹砂岩等全风化地基承载力σ0=200kPa、强风化泥岩地基承载力σ0=600kPa。'
    query = '看看知识库里 铁路工程地质原位测试规程 TB_10018-2018.pdf 写的是啥'
    history = []

    print(f'Query: {query}')
    print('-' * 60)
    result = agentic_forward(query, history)
    print('Result:')
    print(result)
