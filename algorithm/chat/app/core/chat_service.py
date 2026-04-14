from __future__ import annotations
import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union
import lazyllm
from lazyllm import LOG
from fastapi.responses import StreamingResponse
from chat.config import (URL_MAP, RAG_MODE, MULTIMODAL_MODE, MAX_CONCURRENCY,
                         LAZYRAG_LLM_PRIORITY, SENSITIVE_FILTER_RESPONSE_TEXT)
from chat.utils.helpers import validate_and_resolve_files
from chat.app.core.chat_server import chat_server


rag_sem = asyncio.Semaphore(MAX_CONCURRENCY)


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
                       image_files: List[str], priority: Optional[int]) -> Dict[str, Any]:
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
        'debug': debug, 'databases': databases if RAG_MODE and databases else [], 'priority': priority
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
                      priority: Optional[int], is_stream: bool) -> Union[Dict[str, Any], StreamingResponse]:
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
        )

        try:
            async with rag_sem:
                lazyllm.globals._init_sid(sid=session_id)
                lazyllm.locals._init_sid(sid=session_id)
                result = await _run_sync_ppl(
                    bool(reasoning), dataset, query_params, query, filters, priority
                )
                cost = round(time.time() - start_time, 3)
                return _resp(200, 'success', result, cost)
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
                    async_result = await asyncio.to_thread(ppl, *args)
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
                        query: str, filters: Optional[Dict[str, Any]], priority: Any) -> Any:
    if reasoning:
        return await asyncio.to_thread(
            chat_server.query_ppl_reasoning,
            {'query': query},
            {
                'kb_search': {
                    'filters': filters,
                    'files': [],
                    'stream': False,
                    'priority': priority,
                    'document_url': URL_MAP[dataset],
                }
            },
            False,
        )
    return await asyncio.to_thread(chat_server.get_query_pipeline(dataset), query_params)
