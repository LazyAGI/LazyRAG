from __future__ import annotations

import logging
import os
from pathlib import Path

from .base import EvalProvider, TraceProvider
from .http_eval import HttpEvalProvider
from .langfuse_trace import LangfuseTraceProvider
from .mock_eval import MockEvalProvider
from .mock_trace import MockTraceProvider
from .trace_cache import CachedTraceProvider, TraceCache, write_bundle
from .trace_schema import normalize_step, normalize_trace

_log = logging.getLogger('evo.providers')

__all__ = [
    'EvalProvider', 'TraceProvider',
    'HttpEvalProvider', 'LangfuseTraceProvider',
    'MockEvalProvider', 'MockTraceProvider',
    'CachedTraceProvider', 'TraceCache', 'write_bundle',
    'normalize_step', 'normalize_trace',
    'get_eval_provider', 'get_trace_provider',
]


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / 'data'


def get_eval_provider(*, mock_path: Path | str | None = None) -> EvalProvider:
    kind = os.getenv('EVO_EVAL_PROVIDER')
    if kind is None:
        _log.warning('EVO_EVAL_PROVIDER unset, falling back to mock; '
                      'set EVO_EVAL_PROVIDER=http for production')
        kind = 'mock'
    kind = kind.lower()
    if kind == 'http':
        return HttpEvalProvider(base_url=os.environ['EVO_EVAL_BASE_URL'],
                                token=os.getenv('EVO_EVAL_TOKEN', ''))
    if kind == 'mock':
        path = (Path(mock_path) if mock_path
                else Path(os.environ.get('EVO_EVAL_MOCK_PATH')
                          or _default_data_dir() / 'eval_mock.json'))
        return MockEvalProvider(path)
    raise ValueError(f'unknown EVO_EVAL_PROVIDER={kind!r}')


def get_trace_provider(*, mock_path: Path | str | None = None) -> TraceProvider:
    kind = os.getenv('EVO_TRACE_PROVIDER')
    if kind is None:
        _log.warning('EVO_TRACE_PROVIDER unset, falling back to mock; '
                      'set EVO_TRACE_PROVIDER=langfuse for production')
        kind = 'mock'
    kind = kind.lower()
    if kind == 'langfuse':
        return LangfuseTraceProvider()
    if kind == 'mock':
        path = (Path(mock_path) if mock_path
                else Path(os.environ.get('EVO_TRACE_MOCK_PATH')
                          or _default_data_dir() / 'trace_mock.json'))
        return MockTraceProvider(path)
    raise ValueError(f'unknown EVO_TRACE_PROVIDER={kind!r}')
