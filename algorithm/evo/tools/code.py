'''Source-code inspection tools.

Path access is sandboxed by ``session.config.code_access.read_scope`` (not
``code_map``). ``code_map`` only describes user-modifiable files for the
future fix-applier stage.
'''

from __future__ import annotations

import ast
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.read_scope import (
    is_readable, iter_package_files, iter_scope_files, resolve_in_scope,
)
from evo.runtime.session import get_current_session

_MAX_FILE_CHARS = 4000
_MAX_SEARCH_MATCHES = 30
_DEFAULT_SUFFIXES = ('.py', '.yaml', '.yml', '.json', '.toml', '.md')


def _scope():
    s = get_current_session()
    return s.config.code_access.read_scope if s else None


def _validate_path(file_path: str) -> Path:
    sc = _scope()
    if sc is None:
        raise ValueError('No code_access configured.')
    return resolve_in_scope(file_path, sc)


def _summ_code_map(result: ToolResult[Any]) -> str:
    files = [e['path'] for e in (result.data or {}).get('files', [])][:8]
    return f'{len(files)} files: {files}'


@tool(tags=['code'], summarizer=_summ_code_map)
def list_code_map() -> ToolResult[dict[str, Any]]:
    '''List user-modifiable files (code_map). NOT a read access list.'''
    sess = get_current_session()
    if sess is None:
        return ToolResult.failure('list_code_map', ErrorCode.DATA_NOT_LOADED, 'No session')
    cm = sess.config.code_access.code_map
    entries: list[dict[str, Any]] = []
    for path_str, desc in cm.items():
        p = Path(path_str)
        info: dict[str, Any] = {'path': path_str, 'description': desc, 'exists': p.exists()}
        if p.exists():
            info['size_bytes'] = p.stat().st_size
            info['lines'] = sum(1 for _ in open(p, encoding='utf-8', errors='replace'))
            info['suffix'] = p.suffix
        entries.append(info)
    return ToolResult.success('list_code_map', {
        'files': entries, 'total': len(entries),
        'note': 'code_map = modifiable files only; for reading other files, '
                'use read_source_file (path) or resolve_import (symbol).',
    })


def _summ_subject_index(result: ToolResult[Any]) -> str:
    d = result.data or {}
    return (f'entry={d.get('subject_entry')}; '
            f'steps={list(d.get('step_to_source', {}).keys())}; '
            f'symbols={list(d.get('symbol_hints', {}).keys())}')


@tool(tags=['code'], summarizer=_summ_subject_index)
def list_subject_index() -> ToolResult[dict[str, Any]]:
    '''Return subject_entry + step_to_source + symbol_hints (navigation map).'''
    sess = get_current_session()
    if sess is None:
        return ToolResult.failure('list_subject_index', ErrorCode.DATA_NOT_LOADED, 'No session')
    si = sess.config.code_access.subject_index
    return ToolResult.success('list_subject_index', {
        'subject_entry': str(si.subject_entry) if si.subject_entry else None,
        'step_to_source': {k: asdict(v) for k, v in si.step_to_source.items()},
        'symbol_hints': dict(si.symbol_hints),
    })


@tool(tags=['code'])
def read_source_file(
    file_path: str, start_line: int = 0, end_line: int = 0,
) -> ToolResult[dict[str, Any]]:
    '''Read a file (line-numbered, truncated to 4KB). Allowed by read_scope.'''
    try:
        resolved = _validate_path(file_path)
    except ValueError as exc:
        return ToolResult.failure('read_source_file', ErrorCode.DATA_NOT_LOADED, str(exc))
    except PermissionError as exc:
        return ToolResult.failure('read_source_file', ErrorCode.INVALID_ARGUMENT, str(exc))

    try:
        all_lines = resolved.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError as exc:
        return ToolResult.failure('read_source_file', ErrorCode.IO_ERROR, str(exc))

    total = len(all_lines)
    s = max(0, (start_line - 1) if start_line > 0 else 0)
    e = end_line if end_line > 0 else total
    selected = all_lines[s:e]
    numbered = '\n'.join(f'{s + i + 1:>5}| {line}' for i, line in enumerate(selected))
    truncated = False
    if len(numbered) > _MAX_FILE_CHARS:
        numbered = numbered[:_MAX_FILE_CHARS] + '\n... [TRUNCATED]'
        truncated = True

    return ToolResult.success('read_source_file', {
        'path': str(resolved),
        'total_lines': total,
        'range': f'{s + 1}-{min(e, total)}',
        'truncated': truncated,
        'content': numbered,
    })


@tool(tags=['code'])
def parse_code_structure(
    file_path: str, symbol_name: str | None = None,
) -> ToolResult[dict[str, Any]]:
    '''Two-mode python source inspection.

    - ``symbol_name=None``: overview (class/function names + line ranges, top-level assignments, imports)
    - ``symbol_name=<name>``: full source of that top-level class/function
    '''
    try:
        resolved = _validate_path(file_path)
    except ValueError as exc:
        return ToolResult.failure('parse_code_structure', ErrorCode.DATA_NOT_LOADED, str(exc))
    except PermissionError as exc:
        return ToolResult.failure('parse_code_structure', ErrorCode.INVALID_ARGUMENT, str(exc))

    try:
        source = resolved.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        return ToolResult.failure('parse_code_structure', ErrorCode.IO_ERROR, str(exc))

    if resolved.suffix == '.py':
        if symbol_name:
            return _zoom_python_symbol(source, symbol_name, str(resolved))
        result = _parse_python_ast(source)
    else:
        if symbol_name:
            return ToolResult.failure(
                'parse_code_structure', ErrorCode.INVALID_ARGUMENT,
                f'symbol_name only supported for .py files; got {resolved.suffix}',
            )
        result = _parse_generic(source)
    result['path'] = str(resolved)
    return ToolResult.success('parse_code_structure', result)


def _zoom_python_symbol(source: str, symbol_name: str,
                        file_path: str) -> ToolResult[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ToolResult.failure('parse_code_structure', ErrorCode.IO_ERROR,
                                  f'parse error: {exc}')
    target = next(
        (n for n in tree.body
         if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == symbol_name),
        None,
    )
    if target is None:
        names = [n.name for n in tree.body
                 if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
        return ToolResult.failure(
            'parse_code_structure', ErrorCode.INVALID_ARGUMENT,
            f'symbol {symbol_name!r} not found; available: {names}',
        )
    end_line = getattr(target, 'end_lineno', target.lineno)
    lines = source.splitlines()
    snippet = '\n'.join(lines[target.lineno - 1: end_line])
    payload: dict[str, Any] = {
        'path': file_path, 'symbol': symbol_name,
        'kind': 'class' if isinstance(target, ast.ClassDef) else 'function',
        'start_line': target.lineno, 'end_line': end_line,
        'source': snippet,
    }
    if isinstance(target, ast.ClassDef):
        payload['methods'] = [
            {'name': m.name, 'line': m.lineno, 'args': [a.arg for a in m.args.args]}
            for m in target.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    return ToolResult.success('parse_code_structure', payload)


def _parse_python_ast(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {'parse_error': str(exc), 'classes': [], 'functions': [],
                'assignments': [], 'imports': []}
    classes: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                {'name': m.name, 'args': [a.arg for a in m.args.args], 'line': m.lineno}
                for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({'name': node.name, 'line': node.lineno, 'methods': methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not any(node.lineno >= c['line'] for c in classes):
                functions.append({'name': node.name,
                                   'args': [a.arg for a in node.args.args],
                                   'line': node.lineno})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        val = ast.literal_eval(node.value)
                    except Exception:
                        try:
                            val = ast.unparse(node.value)
                        except Exception:
                            val = ast.dump(node.value)
                        val = val[:200]
                    assignments.append({'name': target.id, 'value': val, 'line': node.lineno})
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                imports.append(f'from {node.module} import '
                               + ', '.join(a.name for a in node.names))
            else:
                imports.extend(a.name for a in node.names)
    return {'classes': classes, 'functions': functions,
            'assignments': assignments, 'imports': imports}


def _parse_generic(source: str) -> dict[str, Any]:
    assignments: list[dict[str, Any]] = []
    kv = re.compile(r'^[\s]*([A-Za-z_][\w]*)\s*[:=]\s*(.+)', re.MULTILINE)
    for i, line in enumerate(source.splitlines(), 1):
        m = kv.match(line)
        if m:
            assignments.append({'name': m.group(1).strip(),
                                 'value': m.group(2).strip(), 'line': i})
    return {'classes': [], 'functions': [], 'assignments': assignments[:60], 'imports': []}


@tool(tags=['code'])
def extract_config_values(
    file_path: str, keys: list[str] | None = None,
) -> ToolResult[dict[str, Any]]:
    '''Look for variable / key assignments in a file.

    - ``keys=None`` or empty: scan default tunable-param vocabulary
      (topk/top_k/top_n/threshold/temperature/chunk_size/score/...)
    - ``keys=[...]``: search the given names (case-insensitive)
    '''
    try:
        resolved = _validate_path(file_path)
    except ValueError as exc:
        return ToolResult.failure('extract_config_values', ErrorCode.DATA_NOT_LOADED, str(exc))
    except PermissionError as exc:
        return ToolResult.failure('extract_config_values', ErrorCode.INVALID_ARGUMENT, str(exc))

    try:
        lines = resolved.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError as exc:
        return ToolResult.failure('extract_config_values', ErrorCode.IO_ERROR, str(exc))

    if not keys:
        return _scan_default_params(str(resolved), lines)

    found: list[dict[str, Any]] = []
    matched: set[str] = set()
    for key in keys:
        pat = re.compile(rf'\b{re.escape(key)}\b\s*[:=]', re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if pat.search(line):
                ctx_start = max(0, i - 2)
                ctx_end = min(len(lines), i + 2)
                context = '\n'.join(
                    f'{ctx_start + j + 1:>5}| {lines[ctx_start + j]}'
                    for j in range(ctx_end - ctx_start)
                )
                found.append({'key': key, 'line': i,
                               'raw_line': line.strip(), 'context': context})
                matched.add(key)
    missing = [k for k in keys if k not in matched]
    return ToolResult.success('extract_config_values', {
        'found': found, 'missing': missing, 'file': str(resolved),
    })


_DEFAULT_PARAM_PATTERN = re.compile(
    r'\b(top_?k|top_?n|threshold|similarity_cut_off|chunk_size|temperature|'
    r'max_tokens|score|max_retries|timeout|model|source|type)\b\s*[:=]',
    re.IGNORECASE,
)


def _scan_default_params(file_path: str, lines: list[str]) -> ToolResult[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for i, line in enumerate(lines, 1):
        m = _DEFAULT_PARAM_PATTERN.search(line)
        if m:
            found.append({'key': m.group(1), 'line': i, 'raw_line': line.strip()})
    return ToolResult.success('extract_config_values', {
        'found': found, 'missing': [], 'file': file_path,
        'scanned_with_default_vocabulary': True,
    })


@tool(tags=['code'])
def search_code_pattern(
    pattern: str,
    file_paths: list[str] | None = None,
    scope: Literal['project', 'package', 'all'] = 'project',
    package: str | None = None,
) -> ToolResult[dict[str, Any]]:
    '''Regex search across files.

    - file_paths given: search those (each validated against read_scope)
    - scope='project': recursive over project_roots+extra_roots (default suffixes)
    - scope='package' + package='<pkg>': recursive over that third-party package
    - scope='all': both
    '''
    if not pattern:
        return ToolResult.failure('search_code_pattern', ErrorCode.INVALID_ARGUMENT,
                                  'pattern is required.')
    sc = _scope()
    if sc is None:
        return ToolResult.failure('search_code_pattern', ErrorCode.DATA_NOT_LOADED,
                                  'No code_access configured.')
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return ToolResult.failure('search_code_pattern', ErrorCode.INVALID_ARGUMENT,
                                  f'Invalid regex: {exc}')

    targets: list[Path] = []
    if file_paths:
        for fp in file_paths:
            ok, _ = is_readable(fp, sc)
            if ok:
                targets.append(Path(fp).resolve())
    else:
        if scope in ('project', 'all'):
            targets.extend(iter_scope_files(sc, suffixes=_DEFAULT_SUFFIXES))
        if scope in ('package', 'all'):
            if not package:
                if scope == 'package':
                    return ToolResult.failure(
                        'search_code_pattern', ErrorCode.INVALID_ARGUMENT,
                        "scope='package' requires package='<name>'",
                    )
            else:
                targets.extend(iter_package_files(package, suffixes=_DEFAULT_SUFFIXES))

    matches: list[dict[str, Any]] = []
    for p in targets:
        try:
            lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append({'file': str(p), 'line': i, 'text': line.strip()})
                if len(matches) >= _MAX_SEARCH_MATCHES:
                    break
        if len(matches) >= _MAX_SEARCH_MATCHES:
            break

    return ToolResult.success('search_code_pattern', {
        'matches': matches, 'total': len(matches),
        'truncated': len(matches) >= _MAX_SEARCH_MATCHES,
        'pattern': pattern, 'scope': scope, 'package': package,
        'files_scanned': len(targets),
    })
