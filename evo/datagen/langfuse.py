from __future__ import annotations

import dataclasses
import logging
import time
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
    from lazyllm.tracing.consume import get_single_trace
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return normalize_trace(dataclasses.asdict(get_single_trace(trace_id)))
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(delay_s)
    raise last_exc or RuntimeError(f'trace fetch failed for {trace_id}')


def fetch_traces_for_report(report: dict, max_workers: int = 8) -> dict[str, Any]:
    out: dict[str, Any] = {}
    trace_ids: list[str] = []
    for case in report.get('case_details') or []:
        trace_id = case.get('trace_id')
        if not trace_id or trace_id in trace_ids or trace_id == 'mock':
            continue
        if isinstance(case.get('rag_trace'), dict):
            out[trace_id] = normalize_trace(case['rag_trace'])
            continue
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
                out[trace_id] = {'trace_id': trace_id, 'error': str(exc)}
    return out
