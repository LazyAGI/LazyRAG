from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any

from lazyllm import LOG
import lazyllm.tracing.collect.configs  # noqa: F401
from lazyllm.tracing.collect import runtime as tracing_runtime
from lazyllm.tracing.datamodel.raw import RawSpanRecord, RawTracePayload, RawTraceRecord

try:
    from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
except Exception:  # pragma: no cover - depends on LazyLLM tracing extras.
    ReadableSpan = Any  # type: ignore

    class SpanProcessor:  # type: ignore
        pass


_SINK: LocalTraceSink | None = None
_SINK_LOCK = threading.Lock()
_DEFAULT_MAX_TRACES = 512
_DEFAULT_TTL_S = 3600


def local_trace_enabled() -> bool:
    return os.getenv('LAZYRAG_LOCAL_TRACE_SINK', '1').lower() in {'1', 'true', 'yes', 'on'}


def ensure_local_trace_sink() -> 'LocalTraceSink | None':
    if not local_trace_enabled():
        return None
    global _SINK
    if _SINK is not None:
        return _SINK
    with _SINK_LOCK:
        if _SINK is not None:
            return _SINK
        if not tracing_runtime.tracing_available():
            raise RuntimeError('LazyLLM tracing runtime is not available; local trace sink cannot be installed')
        provider = getattr(tracing_runtime._runtime, '_provider', None)
        if provider is None:
            raise RuntimeError('LazyLLM tracing provider is not initialized; local trace sink cannot be installed')
        _SINK = LocalTraceSink(
            max_traces=int(os.getenv('LAZYRAG_LOCAL_TRACE_MAX_TRACES', str(_DEFAULT_MAX_TRACES))),
            ttl_s=float(os.getenv('LAZYRAG_LOCAL_TRACE_TTL_S', str(_DEFAULT_TTL_S))),
        )
        provider.add_span_processor(_SINK)
        LOG.info('[ChatServer] local trace sink installed')
        return _SINK


class LocalTraceSink(SpanProcessor):
    def __init__(self, *, max_traces: int, ttl_s: float) -> None:
        self._max_traces = max(1, max_traces)
        self._ttl_s = max(1.0, ttl_s)
        self._lock = threading.RLock()
        self._spans_by_trace: OrderedDict[str, list[RawSpanRecord]] = OrderedDict()
        self._updated_at: dict[str, float] = {}

    def on_start(self, span: Any, parent_context: Any | None = None) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        try:
            record = _raw_span_from_readable(span)
        except Exception as exc:
            LOG.warning(f'[ChatServer] [LOCAL_TRACE_SPAN_DROPPED] {exc}')
            return
        with self._lock:
            rows = self._spans_by_trace.setdefault(record.trace_id, [])
            rows.append(record)
            self._spans_by_trace.move_to_end(record.trace_id)
            self._updated_at[record.trace_id] = time.time()
            self._prune_locked()

    def shutdown(self) -> None:
        with self._lock:
            self._spans_by_trace.clear()
            self._updated_at.clear()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            spans = list(self._spans_by_trace.get(trace_id) or [])
            if not spans:
                return None
            self._spans_by_trace.move_to_end(trace_id)
        trace = _raw_trace_from_spans(trace_id, spans)
        payload = RawTracePayload(trace=trace, spans=spans)
        structured = _rebuild_trace(payload)
        return dataclasses.asdict(structured)

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [tid for tid, ts in self._updated_at.items() if now - ts > self._ttl_s]
        for tid in expired:
            self._updated_at.pop(tid, None)
            self._spans_by_trace.pop(tid, None)
        while len(self._spans_by_trace) > self._max_traces:
            tid, _ = self._spans_by_trace.popitem(last=False)
            self._updated_at.pop(tid, None)


def _rebuild_trace(payload: RawTracePayload) -> Any:
    try:
        from lazyllm.tracing.consume.reconstruction import rebuild
    except ImportError:
        from lazyllm.tracing.consume.reconstruction.tree import rebuild
    return rebuild(payload.trace, payload.spans)


def _raw_trace_from_spans(trace_id: str, spans: list[RawSpanRecord]) -> RawTraceRecord:
    root = next((s for s in spans if _as_bool(s.attributes.get('lazyllm.span.is_root'))), None)
    first = min(spans, key=lambda s: s.start_time)
    source = root or first
    attrs = source.attributes
    tags = _parse_list(attrs.get('lazyllm.trace.tags'))
    metadata = {
        key.removeprefix('lazyllm.trace.metadata.'): value
        for key, value in attrs.items()
        if key.startswith('lazyllm.trace.metadata.')
    }
    return RawTraceRecord(
        trace_id=trace_id,
        name=_as_str(attrs.get('lazyllm.trace.name')) or source.name or trace_id,
        session_id=_as_str(attrs.get('session.id')),
        user_id=_as_str(attrs.get('user.id')),
        tags=tags,
        metadata=metadata,
        input=source.input,
        output=source.output,
        start_time=min(s.start_time for s in spans),
        end_time=max((s.end_time or s.start_time for s in spans), default=None),
        status='error' if any(s.status == 'error' for s in spans) else 'ok',
        raw={},
    )


def _raw_span_from_readable(span: ReadableSpan) -> RawSpanRecord:
    ctx = span.get_span_context()
    trace_id = f'{ctx.trace_id:032x}'
    span_id = f'{ctx.span_id:016x}'
    parent = getattr(span, 'parent', None)
    parent_span_id = f'{parent.span_id:016x}' if parent is not None and getattr(parent, 'is_valid', False) else None
    attrs = dict(getattr(span, 'attributes', None) or {})
    status_obj = getattr(span, 'status', None)
    status_code = getattr(status_obj, 'status_code', None)
    status_name = getattr(status_code, 'name', '')
    return RawSpanRecord(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=getattr(span, 'name', '') or attrs.get('lazyllm.entity.name') or '',
        start_time=_ns_to_epoch(getattr(span, 'start_time', None)),
        end_time=_optional_ns_to_epoch(getattr(span, 'end_time', None)),
        status='error' if str(status_name).upper() == 'ERROR' else 'ok',
        attributes=attrs,
        input=_decode_payload(attrs.get('lazyllm.io.input')),
        output=_decode_payload(attrs.get('lazyllm.io.output')),
        metadata={'attributes': attrs},
        error_message=_as_str(attrs.get('lazyllm.error.message')) or getattr(status_obj, 'description', None),
        raw={},
    )


def _ns_to_epoch(value: int | None) -> float:
    return float(value or 0) / 1_000_000_000.0


def _optional_ns_to_epoch(value: int | None) -> float | None:
    return None if value is None else _ns_to_epoch(value)


def _decode_payload(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {'1', 'true', 'yes', 'on'}
    return False
