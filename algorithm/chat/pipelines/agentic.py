from __future__ import annotations

# ruff: noqa: E402

import asyncio
import json
import os
import re
import sys
import threading
from functools import lru_cache
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, Optional

import lazyllm
from lazyllm import loop, once_wrapper
from lazyllm.tools.agent.functionCall import FunctionCall
from lazyllm.tools.fs.client import FS
from lazyllm.tools.sandbox.sandbox_base import create_sandbox  # noqa: F401


from chat.components.agentic.config import (  # noqa: E402
    _build_runtime_system_prompt,
    _env_int,
    _filter_tools_for_request,
    _get_runtime_agent_defaults,
    _normalize_available_skills,
    _normalize_available_tools,
    _sync_request_context,
)
from chat.components.agentic.history import (  # noqa: E402
    _count_tool_turns,
    _count_user_turns,
    _format_non_stream_result,
    _normalize_history_for_agent,
    _reset_citation_state,
)
from chat.components.agentic.review import _decide_review_mode, _spawn_background_review  # noqa: E402
from chat.components.agentic.tool_stream import (  # noqa: E402
    _STREAM_CHUNK_SIZE,
    _format_tool_stream_frame,
    _iter_text_chunks,
    _normalize_tool_call,
    _stream_frame,
    _tool_call_id,
)
from chat.pipelines.builders.get_models import get_automodel  # noqa: E402


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
                        'type': 'function',
                        'function': {
                            'name': match.group(1),
                            'arguments': json.loads(match.group(2)),
                        },
                    }]
                except json.JSONDecodeError:
                    pass
        tool_calls = []
        if isinstance(llm_output, dict):
            for idx, tc in enumerate((llm_output.get('tool_calls') or []), start=1):
                if not isinstance(tc, dict):
                    continue
                normalized_tool_call = _normalize_tool_call(tc)
                normalized_tool_call['id'] = _tool_call_id(
                    normalized_tool_call, self._round_index, idx
                )
                tool_calls.append(normalized_tool_call)
            if tool_calls:
                llm_output['tool_calls'] = [
                    {
                        'id': tool_call['id'],
                        'type': 'function',
                        'function': {
                            'name': tool_call.get('name', ''),
                            'arguments': json.dumps(
                                tool_call.get('arguments', {}),
                                ensure_ascii=False,
                            ),
                        },
                    }
                    for tool_call in tool_calls
                ]

        if self._stream_event_callback and isinstance(llm_output, dict) and tool_calls:
            self._stream_event_callback({
                'round': self._round_index,
                'content': llm_output.get('content', ''),
                'tool_calls': tool_calls,
                'tool_results': [],
            })

        result = super()._post_action(llm_output)

        if self._stream_event_callback and isinstance(llm_output, dict) and tool_calls:
            tool_call_trace = (
                lazyllm.locals.get('_lazyllm_agent', {})
                .get('workspace', {})
                .get('tool_call_trace', [])
            )
            self._stream_event_callback({
                'round': self._round_index,
                'content': '',
                'tool_calls': [],
                'tool_results': [
                    {
                        'id': tool_call.get('id', ''),
                        'tool_name': tool_call.get('name', ''),
                        'result': tool_trace.get('tool_call_result'),
                    }
                    for tool_call, tool_trace in zip(tool_calls, tool_call_trace)
                    if isinstance(tool_trace, dict)
                ],
            })
        return result


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


def agentic_forward(
    query: str,
    history: list[dict[str, Any]],
    stream_event_callback=None,
) -> Any:
    config = lazyllm.globals.get('agentic_config') or {}
    if not isinstance(config, dict):
        config = {}

    llm = get_automodel('llm')
    available_tools = _filter_tools_for_request(
        _normalize_available_tools(config.get('available_tools')),
        config,
    )
    available_skills = _normalize_available_skills(config.get('available_skills'))
    skills_dir = config.get('skill_fs_url') or ''
    config['available_tools'] = available_tools
    config['available_skills'] = available_skills

    keep_full_turns = config.get('keep_full_turns', 3)
    runtime_prompt = _build_runtime_system_prompt(config, available_tools)
    agent_cls = _StreamingReactAgent if stream_event_callback else lazyllm.tools.agent.ReactAgent
    agent_kwargs = {
        'llm': llm,
        'tools': available_tools,
        'max_retries': _env_int('LAZYRAG_MAX_RETRIES', 20),
        'return_trace': config.get('return_trace', False),
        'stream': bool(stream_event_callback),
        'prompt': runtime_prompt,
        'skills': available_skills,
        'workspace': config.get('workspace', './workspace'),
        'keep_full_turns': keep_full_turns,
        'fs': FS,
        'skills_dir': skills_dir,
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
        history_snapshot = (
            [{'role': 'system', 'content': runtime_prompt}]
            + history_snapshot
            + [{'role': 'assistant', 'content': agent_output}]
        )
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
            keep_full_turns=keep_full_turns,
            history_snapshot=history_snapshot,
            review_mode=review_mode,
            request_global_sid=request_global_sid,
        )

    return agent_output


def _lazyllm_queue_db_path() -> Path:
    from lazyllm.configs import config

    home = Path(os.path.expanduser(config['home']))
    return home / '.lazyllm_filesystem_queue.db'


def _clear_orphaned_lazyllm_queue_lock() -> None:
    db_path = _lazyllm_queue_db_path()
    lock_path = Path(f'{db_path}.lock')
    if lock_path.exists() and not db_path.exists():
        lock_path.unlink(missing_ok=True)


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
    streamed_text = False

    lazyllm.globals._init_sid(global_sid)
    lazyllm.locals._init_sid(local_sid)
    _clear_orphaned_lazyllm_queue_lock()
    lazyllm.FileSystemQueue().clear()
    lazyllm.FileSystemQueue.get_instance('think').clear()

    def _emit_event(event: dict[str, Any]) -> None:
        if not closed.is_set():
            event_queue.put({'type': 'tool_event', 'event': event})

    def _drain_stream_frames() -> list[dict[str, Any]]:
        nonlocal streamed_text
        frames: list[dict[str, Any]] = []

        lazyllm.FileSystemQueue.get_instance('think').dequeue()

        text_values = lazyllm.FileSystemQueue().dequeue()
        if text_values:
            text = ''.join(text_values)
            if text:
                streamed_text = True
                frames.append(_stream_frame(text=text))

        return frames

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
            for frame in _drain_stream_frames():
                yield frame

            try:
                event = await asyncio.to_thread(event_queue.get, True, 0.05)
            except Empty:
                continue

            if event is sentinel:
                break
            if isinstance(event, Exception):
                raise event
            if isinstance(event, dict) and event.get('type') == 'final':
                final_result = event.get('result')
            elif isinstance(event, dict) and event.get('type') == 'tool_event':
                for frame in _drain_stream_frames():
                    yield frame
                tool_event = event.get('event') or {}
                frame = _format_tool_stream_frame(tool_event)
                if frame is None:
                    continue
                yield frame

        for frame in _drain_stream_frames():
            yield frame

        output = _format_non_stream_result(final_result, runtime_params)
        chunk_size = int(runtime_params.get('stream_chunk_size') or _STREAM_CHUNK_SIZE)
        if not streamed_text:
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
    from chat.tools import kb, memory, skill_manager, web_search  # noqa: F401


@lru_cache(maxsize=1)
def _get_cwd() -> str:
    return str(Path.cwd())


def get_ppl_agentic():
    return agentic_rag


def agentic_rag(
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
    history = _normalize_history_for_agent(history)

    runtime_params = _get_runtime_agent_defaults()
    runtime_params.update(global_params or {})
    runtime_params.update(kwargs)
    runtime_params['stream'] = stream
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
