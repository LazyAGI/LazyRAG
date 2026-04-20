from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.read_scope import is_readable
from evo.runtime.session import get_current_session


def _summ_resolve(result: ToolResult[Any]) -> str:
    d = result.data or {}
    return (f'{d.get('symbol')} -> {d.get('file')}:{d.get('line')} '
            f'({d.get('kind')}, readable={d.get('readable')})')


@tool(tags=['code'], summarizer=_summ_resolve)
def resolve_import(symbol: str) -> ToolResult[dict[str, Any]]:
    '''Resolve a Python dotted symbol (``pkg.mod.Name``) to its source file/line.

    Supports module / class / function / method / attribute. Marks whether
    the resolved file is readable under the current ``read_scope``.
    '''
    if not symbol or not isinstance(symbol, str):
        return ToolResult.failure('resolve_import', ErrorCode.INVALID_ARGUMENT,
                                  'symbol must be non-empty string')
    sess = get_current_session()
    if sess is None:
        return ToolResult.failure('resolve_import', ErrorCode.DATA_NOT_LOADED, 'No session')

    parts = symbol.split('.')
    obj: Any | None = None
    module = None
    for split in range(len(parts), 0, -1):
        mod_name = '.'.join(parts[:split])
        try:
            module = importlib.import_module(mod_name)
        except Exception:
            continue
        obj = module
        for attr in parts[split:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None:
            break
    if obj is None:
        return ToolResult.failure('resolve_import', ErrorCode.INVALID_ARGUMENT,
                                  f'cannot import {symbol!r}')

    try:
        src_obj = inspect.unwrap(obj) if not inspect.ismodule(obj) else obj
        file = inspect.getsourcefile(src_obj) or inspect.getfile(src_obj)
    except (TypeError, OSError) as exc:
        return ToolResult.failure('resolve_import', ErrorCode.IO_ERROR,
                                  f'no source for {symbol!r}: {exc}')
    try:
        _, line = inspect.getsourcelines(src_obj)
    except (TypeError, OSError):
        line = 1

    kind = (
        'module' if inspect.ismodule(src_obj)
        else 'class' if inspect.isclass(src_obj)
        else 'function' if inspect.isfunction(src_obj) or inspect.ismethod(src_obj)
        else 'attribute'
    )
    sig = ''
    if inspect.isfunction(src_obj) or inspect.isclass(src_obj):
        try:
            sig = str(inspect.signature(src_obj))
        except (TypeError, ValueError):
            sig = ''
    doc = (inspect.getdoc(src_obj) or '')[:240]

    file_path = str(Path(file).resolve())
    readable, why = is_readable(file_path, sess.config.code_access.read_scope)

    return ToolResult.success('resolve_import', {
        'symbol': symbol, 'kind': kind, 'file': file_path, 'line': int(line),
        'signature': sig, 'doc_excerpt': doc,
        'readable': readable, 'scope_reason': why,
    })
