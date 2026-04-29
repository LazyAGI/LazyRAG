from __future__ import annotations

import dataclasses
import os
import logging
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

_log = logging.getLogger('evo.datagen.langfuse')


def normalize_step(step: dict) -> dict:
    return {
        'name': step.get('name', ''),
        'start_time': step.get('start_time', ''),
        'end_time': step.get('end_time', ''),
        'metadata': step.get('metadata', {}),
        'inputs': step.get('inputs', {}),
        'outputs': step.get('outputs', {}),
    }


def normalize_trace(raw: dict) -> dict[str, Any]:
    steps = raw.get('steps', [])
    if isinstance(steps, list):
        steps = [normalize_step(s) for s in steps]
    trace = {
        'trace_id': raw.get('trace_id', ''),
        'name': raw.get('name', ''),
        'start_time': raw.get('start_time', ''),
        'end_time': raw.get('end_time', ''),
        'metadata': raw.get('metadata', {}),
        'steps': steps,
    }
    if isinstance(raw.get('execution_tree'), dict):
        trace['execution_tree'] = raw['execution_tree']
    if isinstance(raw.get('query'), str):
        trace['query'] = raw['query']
    if isinstance(raw.get('modules'), dict):
        trace['modules'] = raw['modules']
    return trace


def fetch_langfuse_trace(trace_id: str, *, attempts: int = 6, delay_s: float = 2.0) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return _fetch_trace_http(trace_id) or _fetch_trace_lazyllm(trace_id)
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(delay_s)
    raise last_exc or RuntimeError(f'trace fetch failed for {trace_id}')


def _fetch_trace_lazyllm(trace_id: str) -> dict[str, Any]:
    from lazyllm.tracing.consume import get_single_trace
    return normalize_trace(dataclasses.asdict(get_single_trace(trace_id)))


def _fetch_trace_http(trace_id: str) -> dict[str, Any] | None:
    host = _clean_env(os.getenv('LANGFUSE_HOST') or os.getenv('LANGFUSE_BASE_URL')).rstrip('/')
    public_key = _clean_env(os.getenv('LANGFUSE_PUBLIC_KEY'))
    secret_key = _clean_env(os.getenv('LANGFUSE_SECRET_KEY'))
    if not (host and public_key and secret_key):
        return None
    resp = requests.get(f'{host}/api/public/traces/{trace_id}',
                        auth=(public_key, secret_key), timeout=30)
    if resp.status_code == 404:
        raise KeyError(trace_id)
    resp.raise_for_status()
    data = resp.json()
    observations = data.get('observations') or []
    modules = _modules_from_observations(observations)
    if not modules:
        modules = {
            data.get('name') or 'trace': {
                'input': data.get('input'),
                'output': data.get('output'),
                'scores': [],
            }
        }
    return normalize_trace({
        'trace_id': data.get('id') or trace_id,
        'name': data.get('name', ''),
        'start_time': data.get('timestamp') or data.get('createdAt') or '',
        'end_time': data.get('updatedAt') or '',
        'metadata': data.get('metadata') or {},
        'steps': observations,
        'query': (data.get('input') or {}).get('query', '') if isinstance(data.get('input'), dict) else '',
        'modules': modules,
    })


def _modules_from_observations(observations: Any) -> dict[str, dict]:
    if not isinstance(observations, list):
        return {}
    modules: dict[str, dict] = {}
    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue
        name = str(obs.get('name') or obs.get('type') or f'observation_{i}')
        key = name if name not in modules else f'{name}_{i}'
        modules[key] = {
            'input': obs.get('input'),
            'output': obs.get('output'),
            'scores': [],
        }
    return modules


def fetch_traces_for_report(report: dict, max_workers: int = 8) -> dict[str, Any]:
    out: dict[str, Any] = {}
    cases_by_trace: dict[str, dict] = {}
    trace_ids: list[str] = []
    for case in report.get('case_details') or []:
        trace_id = case.get('trace_id')
        if not trace_id or trace_id in trace_ids or trace_id == 'mock':
            continue
        if isinstance(case.get('rag_trace'), dict):
            out[trace_id] = normalize_trace(case['rag_trace'])
            continue
        cases_by_trace[trace_id] = case
        trace_ids.append(trace_id)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_langfuse_trace, trace_id): trace_id
                   for trace_id in trace_ids}
        for future in as_completed(futures):
            trace_id = futures[future]
            try:
                out[trace_id] = future.result()
            except Exception as exc:
                _log.warning('trace fetch failed for %s: %s', trace_id, exc)
                out[trace_id] = _trace_from_eval_case(
                    cases_by_trace.get(trace_id, {}), error=str(exc))
    return out


def _clean_env(value: str | None) -> str:
    return (value or '').strip().strip('"').strip("'")


def _trace_from_eval_case(case: dict, *, error: str = '') -> dict[str, Any]:
    trace_id = case.get('trace_id') or ''
    question = case.get('question') or ''
    response = case.get('rag_response') or {}
    data = response.get('data') if isinstance(response.get('data'), dict) else {}
    sources = data.get('sources') or response.get('sources') or []
    answer = case.get('rag_answer') or data.get('text') or data.get('answer') or ''
    modules = {
        'Retriever_KB': {
            'input': {'query': question},
            'output': {
                'sources': sources,
                'contexts': case.get('retrieve_contexts') or [],
                'doc_ids': case.get('retrieve_doc_ids') or [],
                'chunk_ids': case.get('retrieve_chunk_ids') or [],
            },
            'scores': [],
        },
        'AnswerGenerator': {
            'input': {'query': question, 'contexts': case.get('retrieve_contexts') or []},
            'output': {'answer': answer, 'think': data.get('think')},
            'scores': [],
        },
    }
    trace = {
        'trace_id': trace_id,
        'name': 'eval.rag_response',
        'query': question,
        'metadata': {'source': 'eval_report', 'trace_fetch_error': error},
        'modules': modules,
        'steps': [],
    }
    return normalize_trace(trace)
