from __future__ import annotations
import json
import logging
import os
import uuid
import urllib.error
import urllib.request
from typing import Any
_log = logging.getLogger('evo.datagen.rag_client')
class RAGTargetRequiredError(RuntimeError):
    pass
class RAGCallFailed(RuntimeError):
    code = 'RAG_CALL_FAILED'
    kind = 'transient'
class RAGTraceMissing(RuntimeError):
    code = 'RAG_TRACE_MISSING'
    kind = 'permanent'
def call_rag_chat(question: str, target_chat_url: str, dataset_name: str='', filters: dict[str, Any] | None=None) -> dict[str, Any]:
    if not target_chat_url:
        raise RAGTargetRequiredError('target_chat_url is required for RAG evaluation')
    session_id = f'evo-eval-{uuid.uuid4().hex}'
    payload = {'query': question, 'trace': True, 'session_id': session_id}
    if dataset_name:
        payload['dataset'] = dataset_name
    if filters:
        payload['filters'] = filters
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(target_chat_url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        timeout = int(os.getenv('EVO_RAG_TIMEOUT_S', '120'))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        _log.warning('RAG callback failed for %s: %s', target_chat_url, exc)
        raise RAGCallFailed(f'RAG_CALL_FAILED: {exc}') from exc
    if not isinstance(result, dict):
        raise RAGCallFailed(f'RAG_CALL_FAILED: invalid response {type(result).__name__}')
    if result.get('code') not in (None, 200):
        raise RAGCallFailed(f"RAG_CALL_FAILED: {result.get('msg') or result}")
    data_obj = result.get('data') if isinstance(result.get('data'), dict) else {}
    sources = result.get('sources') or data_obj.get('sources') or data_obj.get('recall') or []
    trace_id = result.get('trace_id') or data_obj.get('trace_id') or ''
    if not trace_id:
        trace_id = session_id
        _log.info('target chat omitted trace_id; using session_id %s', trace_id)
    answer = result.get('answer') or data_obj.get('answer') or data_obj.get('text') or data_obj.get('data') or ''
    return {'answer': answer, 'contexts': result.get('contexts') or _pluck_any(sources, ('context', 'content')), 'docs': result.get('docs') or _pluck_any(sources, ('doc', 'file_name')), 'raw': result, 'chunk_ids': result.get('chunk_ids') or _pluck_any(sources, ('chunk_id', 'segment_id', 'segement_id')), 'doc_ids': result.get('doc_ids') or _pluck_any(sources, ('doc_id', 'document_id')), 'trace_id': trace_id, 'trace': data_obj.get('trace') if isinstance(data_obj.get('trace'), dict) else None}
def _pluck_any(sources: Any, keys: tuple[str, ...]) -> list[Any]:
    if not isinstance(sources, list):
        return []
    values: list[Any] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        for key in keys:
            if item.get(key) is not None:
                values.append(item[key])
                break
    return values
