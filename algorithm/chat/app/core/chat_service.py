from __future__ import annotations
import asyncio
import base64
import json
import os
import threading
import uuid
import time
from typing import Any, Dict, List, Optional, Union
import lazyllm
import requests
from lazyllm import LOG
from lazyllm.tracing import current_trace, enable_trace
from lazyllm.tracing.collect import runtime as tracing_runtime
from fastapi.responses import StreamingResponse
from chat.config import (RAG_MODE, MULTIMODAL_MODE, MAX_CONCURRENCY,
                         LAZYRAG_LLM_PRIORITY, SENSITIVE_FILTER_RESPONSE_TEXT,
                         URL_MAP, resolve_dataset_url)
from chat.utils.helpers import validate_and_resolve_files
from chat.app.core.chat_server import chat_server


rag_sem = asyncio.Semaphore(MAX_CONCURRENCY)


def _run_ppl_with_trace(ppl, ppl_args, *, session_id, dataset, mode_tag, trace_enabled):
    if not trace_enabled:
        return ppl(*ppl_args), None, None

    captured: Dict[str, Any] = {}
    started_at = time.time()

    def naive_rag(*args, **kwargs):
        out = ppl(*args, **kwargs)
        ct = current_trace()
        captured['trace_id'] = ct.trace_id if ct else None
        captured['result'] = out
        return out

    enable_trace(
        naive_rag, *ppl_args,
        session_id=session_id,
        request_tags=[f'dataset:{dataset}', f'mode:{mode_tag}'],
    )
    result = captured.get('result')
    trace_id = captured.get('trace_id') or uuid.uuid4().hex
    _export_trace_async(trace_id, ppl_args, result,
                        session_id=session_id, dataset=dataset,
                        mode_tag=mode_tag)
    local_trace = None if captured.get('trace_id') else {
        'trace_id': trace_id,
        'name': 'chat.pipelines.naive',
        'query': ppl_args[0].get('query', '') if ppl_args and isinstance(ppl_args[0], dict) else '',
        'modules': {
            'naive.py': {
                'input': ppl_args[0] if ppl_args else None,
                'output': result,
            }
        },
        'metadata': {'dataset': dataset, 'mode': mode_tag, 'session_id': session_id},
        'steps': [{
            'name': 'naive.py',
            'start_time': started_at,
            'end_time': time.time(),
            'metadata': {'fallback': True},
            'inputs': {'args': [str(a)[:4000] for a in ppl_args]},
            'outputs': {'result': str(result)[:4000]},
        }],
    }
    return result, trace_id, local_trace


def _export_trace_async(trace_id: str, ppl_args: tuple, result: Any, *,
                        session_id: str, dataset: str, mode_tag: str) -> None:
    def run() -> None:
        _flush_trace_exporter()
        _ingest_langfuse_trace(trace_id, ppl_args, result,
                               session_id=session_id, dataset=dataset,
                               mode_tag=mode_tag)

    threading.Thread(target=run, daemon=True,
                     name=f'chat-trace-export-{trace_id[:8]}').start()


def _flush_trace_exporter() -> None:
    provider = getattr(tracing_runtime._runtime, '_provider', None)
    if provider is None:
        return
    try:
        timeout_ms = int(os.getenv('LANGFUSE_FORCE_FLUSH_TIMEOUT_MS', '5000'))
        provider.force_flush(timeout_millis=timeout_ms)
    except Exception as exc:
        LOG.warning(f'[ChatServer] [TRACE_FLUSH_FAILED] {exc}')


def _ingest_langfuse_trace(trace_id: str, ppl_args: tuple, result: Any, *,
                           session_id: str, dataset: str, mode_tag: str) -> None:
    host = _clean_env(os.getenv('LANGFUSE_HOST') or os.getenv('LANGFUSE_BASE_URL')).rstrip('/')
    public_key = _clean_env(os.getenv('LANGFUSE_PUBLIC_KEY'))
    secret_key = _clean_env(os.getenv('LANGFUSE_SECRET_KEY'))
    if not host or not public_key or not secret_key:
        return
    query_payload = ppl_args[0] if ppl_args else None
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    auth = base64.b64encode(f'{public_key}:{secret_key}'.encode()).decode('ascii')
    headers = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}
    batch = [
        {
            'id': uuid.uuid4().hex,
            'type': 'trace-create',
            'timestamp': now,
            'body': {
                'id': trace_id,
                'name': 'chat.pipelines.naive',
                'sessionId': session_id,
                'input': query_payload,
                'output': result,
                'metadata': {'dataset': dataset, 'mode': mode_tag},
            },
        },
        {
            'id': uuid.uuid4().hex,
            'type': 'span-create',
            'timestamp': now,
            'body': {
                'id': uuid.uuid4().hex[:16],
                'traceId': trace_id,
                'name': 'naive.py',
                'startTime': now,
                'endTime': now,
                'input': query_payload,
                'output': result,
                'metadata': {'dataset': dataset, 'mode': mode_tag},
            },
        },
    ]
    for attempt in range(3):
        try:
            resp = requests.post(f'{host}/api/public/ingestion',
                                 headers=headers, json={'batch': batch},
                                 timeout=45)
            if resp.status_code == 207 and not (resp.json().get('errors') or []):
                return
            LOG.warning(f'[ChatServer] [TRACE_INGEST_FAILED] status={resp.status_code} body={resp.text[:500]}')
        except Exception as exc:
            LOG.warning(f'[ChatServer] [TRACE_INGEST_FAILED] attempt={attempt + 1} error={exc}')
        time.sleep(2)


def _clean_env(value: str | None) -> str:
    return (value or '').strip().strip('"').strip("'")


def _sse_line(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str) + '\n\n'


def _resp(code: int, msg: str, data: Any, cost: float) -> Dict[str, Any]:
    return {'code': code, 'msg': msg, 'data': data, 'cost': cost}


def check_sensitive_content(
    query: str, session_id: str, start_time: float
) -> Optional[Dict[str, Any]]:
    if not chat_server.sensitive_filter.loaded:
        return None
    has_sensitive, sensitive_word = chat_server.sensitive_filter.check(query)
    if has_sensitive:
        cost = round(time.time() - start_time, 3)
        LOG.warning(
            f'[ChatServer] [SENSITIVE_FILTER_BLOCKED] [query={query[:50]}...] '
            f'[sensitive_word={sensitive_word}] [session_id={session_id}]'
        )
        return _resp(
            200,
            'success',
            {
                'think': None,
                'text': SENSITIVE_FILTER_RESPONSE_TEXT,
                'sources': [],
            },
            cost,
        )
    return None


def build_query_params(query: str, history: Optional[List[Dict[str, Any]]],
                       filters: Optional[Dict[str, Any]], other_files: List[str],
                       databases: Optional[List[Dict[str, Any]]], debug: bool,
                       image_files: List[str], priority: Optional[int],
                       dataset: Optional[str],
                       session_id: str,
                       available_tools: Optional[List[str]],
                       available_skills: Optional[List[str]],
                       memory: Optional[str],
                       user_preference: Optional[str],
                       use_memory: Optional[bool],
                       create_user_id: Optional[str] = None) -> Dict[str, Any]:
    hist = [
        {
            'role': str(h.get('role', 'assistant')),
            'content': str(h.get('content', '')),
        }
        for h in (history or [])
        if isinstance(h, dict)
    ]
    return {
        'query': query, 'history': hist, 'filters': filters if RAG_MODE and filters else {},
        'files': other_files, 'image_files': image_files if MULTIMODAL_MODE and image_files else [],
        'debug': debug, 'databases': databases if RAG_MODE and databases else [], 'priority': priority,
        'dataset': dataset,
        'session_id': session_id,
        'document_url': URL_MAP.get(dataset, ''),
        'available_tools': available_tools,
        'available_skills': available_skills,
        'memory': memory,
        'user_preference': user_preference,
        'use_memory': use_memory,
        'create_user_id': create_user_id or '',
    }


def log_chat_request(query: str, session_id: str, filters: Optional[Dict[str, Any]],
                     other_files: List[str], databases: Optional[List[Dict[str, Any]]],
                     image_files: List[str], cost: float,
                     response: Any = None, log_type: str = 'KB_CHAT') -> None:
    databases_str = json.dumps(databases, ensure_ascii=False) if databases else []
    response_str = response if response is not None else None
    LOG.info(
        f'[ChatServer] [{log_type}] [query={query}] [session_id={session_id}] '
        f'[filters={filters}] [files={other_files}] [image_files={image_files}] '
        f'[databases={databases_str}] [cost={cost}] [response={response_str}]'
    )


async def handle_chat(query: str, history: Optional[List[Dict[str, Any]]],
                      session_id: str, filters: Optional[Dict[str, Any]],
                      files: Optional[List[str]], debug: Optional[bool], reasoning: Optional[bool],
                      databases: Optional[List[Dict[str, Any]]], dataset: Optional[str],
                      priority: Optional[int], available_tools: Optional[List[str]],
                      available_skills: Optional[List[str]], memory: Optional[str],
                      user_preference: Optional[str], use_memory: Optional[bool],
                      is_stream: bool, trace: bool = False,
                      create_user_id: Optional[str] = None) -> Union[Dict[str, Any], StreamingResponse]:
    result = None
    priority = LAZYRAG_LLM_PRIORITY if priority is None else priority

    if not chat_server.has_dataset(dataset):
        return _resp(400, f'dataset {dataset} not found', None, 0.0)

    start_time = time.time()
    sensitive_check_result = check_sensitive_content(query, session_id, start_time)
    log_tag = 'KB_CHAT_STREAM' if is_stream else 'KB_CHAT'
    LOG.info(f'[ChatServer] [{log_tag}] [query={query}] [sid={session_id}]')

    if not is_stream:
        if sensitive_check_result:
            return sensitive_check_result

        other_files, image_files = validate_and_resolve_files(files)
        query_params = build_query_params(
            query,
            history,
            filters,
            other_files,
            databases,
            debug or False,
            image_files,
            priority,
            dataset,
            session_id,
            available_tools,
            available_skills,
            memory,
            user_preference,
            use_memory,
            create_user_id,
        )

        try:
            async with rag_sem:
                lazyllm.globals._init_sid(sid=session_id)
                lazyllm.locals._init_sid(sid=session_id)
                result, trace_id, local_trace = await _run_sync_ppl(
                    bool(reasoning), dataset, query_params, query, filters, priority,
                    session_id=session_id, trace_enabled=trace,
                )
                cost = round(time.time() - start_time, 3)
                if trace_id is None:
                    data = result
                elif isinstance(result, dict):
                    data = {**result, 'trace_id': trace_id}
                else:
                    data = {'data': result, 'trace_id': trace_id}
                if local_trace is not None and isinstance(data, dict):
                    data['trace'] = local_trace
                return _resp(200, 'success', data, cost)
        except Exception as exc:
            LOG.exception(exc)
            cost = round(time.time() - start_time, 3)
            return _resp(500, f'chat service failed: {exc}', None, cost)
        finally:
            cost = round(time.time() - start_time, 3)
            log_chat_request(
                query, session_id, filters, other_files, image_files, databases, cost, result
            )
    else:
        if sensitive_check_result:

            async def error_stream():
                yield _sse_line(sensitive_check_result)
                yield _sse_line(_resp(200, 'success', {'status': 'FINISHED'}, 0.0))

            return StreamingResponse(error_stream(), media_type='text/event-stream')

        first_frame_logged = False
        other_files, image_files = validate_and_resolve_files(files)
        collected_chunks: List[str] = []

        query_params = build_query_params(
            query,
            history,
            filters,
            other_files,
            databases,
            False,
            image_files,
            priority,
            dataset,
            session_id,
            available_tools,
            available_skills,
            memory,
            user_preference,
            use_memory,
            create_user_id,
        )

        stream_call = (
            (chat_server.query_ppl_reasoning, query_params, None, True)
            if reasoning
            else (chat_server.get_query_pipeline(dataset, stream=True), query_params)
        )

        async def event_stream(ppl, *args) -> Any:
            nonlocal first_frame_logged
            try:
                async with rag_sem:
                    lazyllm.globals._init_sid(sid=session_id)
                    lazyllm.locals._init_sid(sid=session_id)
                    async_result, trace_id, local_trace = await asyncio.to_thread(
                        _run_ppl_with_trace, ppl, args,
                        session_id=session_id, dataset=dataset,
                        mode_tag='stream_reasoning' if reasoning else 'stream',
                        trace_enabled=trace,
                    )
                    if trace_id is not None:
                        payload = {'trace_id': trace_id}
                        if local_trace is not None:
                            payload['trace'] = local_trace
                        yield _sse_line(_resp(200, 'success', payload, 0.0))
                    async for chunk in async_result:
                        now = time.time()
                        if not first_frame_logged:
                            first_cost = round(now - start_time, 3)
                            LOG.info(
                                f'[ChatServer] [KB_CHAT_STREAM_FIRST_FRAME] '
                                f'[query={query}] [session_id={session_id}] '
                                f'[cost={first_cost}]'
                            )
                            first_frame_logged = True

                        chunk_str = (
                            chunk
                            if isinstance(chunk, str)
                            else json.dumps(chunk, ensure_ascii=False)
                        )
                        collected_chunks.append(chunk_str)
                        cost = round(now - start_time, 3)
                        yield _sse_line(_resp(200, 'success', chunk, cost))

            except Exception as exc:
                LOG.exception(exc)
                collected_chunks.append(f'[EXCEPTION]: {str(exc)}')
                final_resp = _resp(
                    500, f'chat service failed: {exc}', {'status': 'FAILED'}, 0.0
                )
            else:
                final_resp = _resp(200, 'success', {'status': 'FINISHED'}, 0.0)

            cost = round(time.time() - start_time, 3)
            final_resp['cost'] = cost
            yield _sse_line(final_resp)

            log_chat_request(query, session_id, filters, other_files, image_files, databases,
                             cost, '\n'.join(collected_chunks), 'KB_CHAT_STREAM_FINISH')

        return StreamingResponse(
            event_stream(*stream_call), media_type='text/event-stream'
        )


async def _run_sync_ppl(reasoning: bool, dataset: str, query_params: Dict[str, Any],
                        query: str, filters: Optional[Dict[str, Any]], priority: Any,
                        *, session_id: str, trace_enabled: bool) -> tuple[Any, Optional[str], Optional[dict]]:
    if reasoning:
        dataset_url = resolve_dataset_url(dataset)
        if dataset_url is None:
            raise KeyError(f'dataset `{dataset}` not found in URL_MAP')
        ppl = chat_server.query_ppl_reasoning
        ppl_args = (
            {'query': query},
            {
                'kb_search': {
                    'filters': filters,
                    'files': [],
                    'stream': False,
                    'priority': priority,
                    'document_url': dataset_url,
                }
            },
            False,
        )
        mode_tag = 'sync_reasoning'
    else:
        ppl = chat_server.get_query_pipeline(dataset)
        ppl_args = (query_params,)
        mode_tag = 'sync'

    return await asyncio.to_thread(
        _run_ppl_with_trace, ppl, ppl_args,
        session_id=session_id, dataset=dataset, mode_tag=mode_tag,
        trace_enabled=trace_enabled,
    )
