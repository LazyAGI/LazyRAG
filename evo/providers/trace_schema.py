from __future__ import annotations

from typing import Any


def _normalize_status(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).lower()
    return 'ok' if s == 'success' else s


def normalize_step(node: dict[str, Any]) -> dict[str, Any]:
    raw = node.get('raw_data') or {}
    return {
        'step_id': node.get('step_id'),
        'name': node.get('name'),
        'node_type': node.get('node_type'),
        'semantic_type': node.get('semantic_type'),
        'status': _normalize_status(node.get('status')),
        'start_time': node.get('start_time'),
        'latency_ms': node.get('latency_ms'),
        'raw_data': {'input': raw.get('input'), 'output': raw.get('output')},
        'semantic_data': node.get('semantic_data'),
        'error_message': node.get('error_message'),
        'children': [normalize_step(c) for c in (node.get('children') or [])],
    }


def normalize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    md = dict(trace.get('metadata') or {})
    md['status'] = _normalize_status(md.get('status'))
    for k in ('name', 'start_time', 'end_time', 'latency_ms',
              'error_message', 'session_id', 'user_id', 'metadata'):
        md.setdefault(k, None)
    md.setdefault('tags', [])
    return {
        'trace_id': trace['trace_id'],
        'metadata': md,
        'execution_tree': normalize_step(trace['execution_tree']),
    }
