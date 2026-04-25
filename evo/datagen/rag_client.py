from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

_log = logging.getLogger('evo.datagen.rag_client')


class RAGTargetRequiredError(RuntimeError):
    pass


class RAGCallFailed(RuntimeError):
    code = 'RAG_CALL_FAILED'
    kind = 'permanent'


def call_rag_chat(question: str, target_chat_url: str, dataset_name: str = '') -> dict[str, Any]:
    if not target_chat_url:
        raise RAGTargetRequiredError('target_chat_url is required for RAG evaluation')
    payload = {'query': question, 'dataset_name': dataset_name}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        target_chat_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        _log.warning('RAG callback failed for %s: %s', target_chat_url, exc)
        raise RAGCallFailed(f'RAG_CALL_FAILED: {exc}') from exc
    data_obj = result.get('data') if isinstance(result.get('data'), dict) else {}
    sources = result.get('sources') or data_obj.get('sources') or []
    return {
        'answer': result.get('answer') or data_obj.get('text') or '',
        'contexts': result.get('contexts') or _pluck(sources, 'context'),
        'docs': result.get('docs') or _pluck(sources, 'doc'),
        'raw': result,
        'chunk_ids': result.get('chunk_ids') or _pluck(sources, 'chunk_id'),
        'doc_ids': result.get('doc_ids') or _pluck(sources, 'doc_id'),
        'trace_id': result.get('trace_id') or data_obj.get('trace_id') or '',
    }


def _pluck(sources: Any, key: str) -> list[Any]:
    if not isinstance(sources, list):
        return []
    return [item[key] for item in sources
            if isinstance(item, dict) and item.get(key) is not None]
