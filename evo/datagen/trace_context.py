from __future__ import annotations

import uuid
from typing import Any


TRACE_CONTEXT_BASE_KEYS = (
    'report_id',
    'dataset_id',
    'knowledge_base_id',
    'algorithm_version',
)

TRACE_CONTEXT_KEYS = (
    'trace_id',
    'scene',
    *TRACE_CONTEXT_BASE_KEYS,
    'case_id',
)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def derive_trace_context(base: dict[str, Any] | None, *, scene: str, case_id: str) -> dict[str, Any]:
    context = {
        key: _clean_value((base or {}).get(key, ''))
        for key in TRACE_CONTEXT_BASE_KEYS
    }
    context.update(
        {
            'trace_id': new_trace_id(),
            'scene': _clean_value(scene),
            'case_id': _clean_value(case_id),
        }
    )
    return {key: context[key] for key in TRACE_CONTEXT_KEYS}


def trace_status(*, require_trace: bool, actual_trace_id: str, expected_trace_id: str | None = None) -> str:
    if not require_trace:
        return 'trace_disabled'
    if not actual_trace_id:
        return 'trace_missing'
    if expected_trace_id and actual_trace_id != expected_trace_id:
        return 'trace_collection_failed'
    return 'success'


def _clean_value(value: Any) -> str:
    return '' if value is None else str(value)


__all__ = [
    'TRACE_CONTEXT_BASE_KEYS',
    'TRACE_CONTEXT_KEYS',
    'derive_trace_context',
    'new_trace_id',
    'trace_status',
]
