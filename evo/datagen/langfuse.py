from __future__ import annotations
import dataclasses
import os
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
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            trace = _fetch_trace_consume(trace_id)
            _assert_trace_complete(trace)
            return trace
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(delay_s)
    raise last_exc or RuntimeError(f'trace fetch failed for {trace_id}')


def _fetch_trace_consume(trace_id: str) -> dict[str, Any]:
    host = _clean_env(os.getenv('LANGFUSE_HOST') or os.getenv('LANGFUSE_BASE_URL'))
    public_key = _clean_env(os.getenv('LANGFUSE_PUBLIC_KEY'))
    secret_key = _clean_env(os.getenv('LANGFUSE_SECRET_KEY'))
    if not (host and public_key and secret_key):
        raise RuntimeError('LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required')
    os.environ.setdefault('LAZYLLM_TRACE_CONSUME_BACKEND', 'langfuse')

    from lazyllm.tracing.consume import get_single_trace

    return normalize_trace(dataclasses.asdict(get_single_trace(trace_id)))


def _assert_trace_complete(trace: dict[str, Any]) -> None:
    tree = trace.get('execution_tree')
    if not isinstance(tree, dict):
        raise RuntimeError(f"trace {trace.get('trace_id')} has no execution_tree")
    names = _execution_node_names(tree)
    # Langfuse observations can be visible slightly before LazyLLM's full tree is
    # consumable. For LazyRAG chat traces, answer/parser are the terminal stages.
    if tree.get('name') == 'run_chat_pipeline' and not {'answer', 'parser'}.issubset(set(names)):
        raise RuntimeError(
            f"trace {trace.get('trace_id')} is not complete yet; "
            f"nodes={names}"
        )


def _execution_node_names(node: dict[str, Any]) -> list[str]:
    names: list[str] = []

    def walk(cur: dict[str, Any]) -> None:
        name = cur.get('name')
        if isinstance(name, str) and name:
            names.append(name)
        for child in cur.get('children') or []:
            if isinstance(child, dict):
                walk(child)

    walk(node)
    return names


def fetch_traces_for_report(report: dict, max_workers: int = 8) -> dict[str, Any]:
    out: dict[str, Any] = {}
    cases_by_trace: dict[str, dict] = {}
    trace_ids: list[str] = []
    for case in report.get('case_details') or []:
        trace_id = case.get('trace_id')
        if not trace_id or trace_id in trace_ids or trace_id == 'mock':
            continue
        if isinstance(case.get('rag_trace'), dict):
            trace = normalize_trace(case['rag_trace'])
            _assert_trace_complete(trace)
            out[trace_id] = trace
            continue
        cases_by_trace[trace_id] = case
        trace_ids.append(trace_id)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_langfuse_trace, trace_id): trace_id for trace_id in trace_ids}
        for future in as_completed(futures):
            trace_id = futures[future]
            try:
                out[trace_id] = future.result()
            except Exception as exc:
                raise RuntimeError(f'trace fetch failed for {trace_id}: {exc}') from exc
    return out


def _clean_env(value: str | None) -> str:
    return (value or '').strip().strip('"').strip("'")
