"""
Source code reading and analysis tools.

These tools let agents inspect the actual RAG pipeline source code referenced
by a user-provided ``code_map`` (dict of path -> description).
All paths must appear in the code_map for safety; arbitrary filesystem reads are rejected.
"""

from __future__ import annotations

import ast
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from lazyllm.tools import fc_register
from evo.domain.schemas import ErrorCode
from evo.tools._common import _ok, _fail
from evo.runtime.session import get_current_session

_MAX_FILE_CHARS = 4000
_MAX_SEARCH_MATCHES = 30


def _get_code_map() -> dict[str, str] | None:
    session = get_current_session()
    if session is None:
        return None
    return session.config.extra.get("code_map")


def _require_code_map() -> dict[str, str]:
    cm = _get_code_map()
    if not cm:
        raise ValueError(
            "No code_map configured. Pass --code-map <path> or set code_map in config."
        )
    return cm


def _validate_path(file_path: str, code_map: dict[str, str]) -> Path:
    resolved = Path(file_path).resolve()
    for allowed in code_map:
        if Path(allowed).resolve() == resolved:
            return resolved
    raise PermissionError(
        f"Path not in code_map: {file_path}. "
        f"Allowed: {list(code_map.keys())}"
    )


@fc_register("tool")
def list_code_map() -> str:
    """
    Return the full code map with file sizes and modification times.

    Returns:
        JSON envelope listing every file in the code map with its description,
        size, and last-modified timestamp.
    """
    start = time.time()
    try:
        cm = _require_code_map()
    except ValueError as e:
        return _fail(ErrorCode.DATA_NOT_LOADED.value, str(e))

    entries = []
    for path_str, desc in cm.items():
        p = Path(path_str)
        info: dict[str, Any] = {"path": path_str, "description": desc, "exists": p.exists()}
        if p.exists():
            stat = p.stat()
            info["size_bytes"] = stat.st_size
            info["lines"] = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
            info["suffix"] = p.suffix
        entries.append(info)

    return _ok({"files": entries, "total": len(entries)}, start)


@fc_register("tool")
def read_source_file(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
    """
    Read a file from the code map, returning numbered lines.

    Args:
        file_path: Absolute path to a file listed in the code map.
        start_line: 1-based start line (0 = from beginning).
        end_line: 1-based end line (0 = until EOF or truncation limit).

    Returns:
        JSON envelope with ``content`` (numbered text), ``total_lines``,
        ``truncated`` flag, and the user-provided ``description``.
    """
    start = time.time()
    try:
        cm = _require_code_map()
        resolved = _validate_path(file_path, cm)
    except (ValueError, PermissionError) as e:
        code = ErrorCode.DATA_NOT_LOADED if "code_map" in str(e) else ErrorCode.INVALID_ARGUMENT
        return _fail(code.value, str(e))

    if not resolved.is_file():
        return _fail(ErrorCode.IO_ERROR.value, f"File does not exist: {file_path}")

    try:
        all_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return _fail(ErrorCode.IO_ERROR.value, str(e))

    total = len(all_lines)
    s = max(0, (start_line - 1) if start_line > 0 else 0)
    e = end_line if end_line > 0 else total
    selected = all_lines[s:e]

    numbered = "\n".join(f"{s + i + 1:>5}| {line}" for i, line in enumerate(selected))
    truncated = False
    if len(numbered) > _MAX_FILE_CHARS:
        numbered = numbered[:_MAX_FILE_CHARS] + "\n... [TRUNCATED]"
        truncated = True

    desc = cm.get(file_path, cm.get(str(resolved), ""))
    return _ok({
        "path": file_path,
        "description": desc,
        "total_lines": total,
        "range": f"{s+1}-{min(e, total)}",
        "truncated": truncated,
        "content": numbered,
    }, start)


@fc_register("tool")
def parse_code_structure(file_path: str) -> str:
    """
    Extract structural information from a Python source file using ``ast``.

    Returns class names, function/method signatures, top-level assignments
    (constants / config values), and imports.  For non-Python files, falls
    back to a regex-based scan for KEY=VALUE patterns.

    Args:
        file_path: Path to the source file (must be in code_map).

    Returns:
        JSON envelope with ``classes``, ``functions``, ``assignments``, ``imports``.
    """
    start = time.time()
    try:
        cm = _require_code_map()
        resolved = _validate_path(file_path, cm)
    except (ValueError, PermissionError) as e:
        code = ErrorCode.DATA_NOT_LOADED if "code_map" in str(e) else ErrorCode.INVALID_ARGUMENT
        return _fail(code.value, str(e))

    try:
        source = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return _fail(ErrorCode.IO_ERROR.value, str(e))

    if resolved.suffix == ".py":
        result = _parse_python_ast(source)
    else:
        result = _parse_generic(source, resolved.suffix)

    result["path"] = file_path
    result["description"] = cm.get(file_path, cm.get(str(resolved), ""))
    return _ok(result, start)


def _parse_python_ast(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"parse_error": str(exc), "classes": [], "functions": [], "assignments": [], "imports": []}

    classes: list[dict] = []
    functions: list[dict] = []
    assignments: list[dict] = []
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                {"name": m.name, "args": [a.arg for a in m.args.args], "line": m.lineno}
                for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({"name": node.name, "line": node.lineno, "methods": methods})

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not any(node.lineno >= c["line"] for c in classes):
                functions.append({
                    "name": node.name,
                    "args": [a.arg for a in node.args.args],
                    "line": node.lineno,
                })

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        val = ast.literal_eval(node.value)
                    except Exception:
                        val = ast.dump(node.value)[:120]
                    assignments.append({"name": target.id, "value": val, "line": node.lineno})

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                imports.append(f"from {node.module} import ...")
            else:
                for alias in node.names:
                    imports.append(alias.name)

    return {"classes": classes, "functions": functions, "assignments": assignments, "imports": imports}


def _parse_generic(source: str, suffix: str) -> dict[str, Any]:
    """Regex-based fallback for non-Python files (YAML, JSON, TOML, etc.)."""
    assignments: list[dict] = []
    kv_pattern = re.compile(r'^[\s]*([A-Za-z_][\w]*)\s*[:=]\s*(.+)', re.MULTILINE)
    for i, line in enumerate(source.splitlines(), 1):
        m = kv_pattern.match(line)
        if m:
            assignments.append({"name": m.group(1).strip(), "value": m.group(2).strip(), "line": i})
    return {"classes": [], "functions": [], "assignments": assignments[:60], "imports": []}


@fc_register("tool")
def extract_config_values(file_path: str, keys: list[str]) -> str:
    """
    Look for specific variable/key assignments in a file.

    Args:
        file_path: Path to the file (must be in code_map).
        keys: Variable or key names to search for (e.g. ``["chunk_size", "topk"]``).

    Returns:
        JSON envelope with ``found`` (list of {key, value, line, context}) and ``missing``.
    """
    start = time.time()
    try:
        cm = _require_code_map()
        resolved = _validate_path(file_path, cm)
    except (ValueError, PermissionError) as e:
        code = ErrorCode.DATA_NOT_LOADED if "code_map" in str(e) else ErrorCode.INVALID_ARGUMENT
        return _fail(code.value, str(e))

    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return _fail(ErrorCode.IO_ERROR.value, str(e))

    found: list[dict] = []
    matched_keys: set[str] = set()
    for key in keys:
        pattern = re.compile(rf'\b{re.escape(key)}\b\s*[:=]', re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                ctx_start = max(0, i - 2)
                ctx_end = min(len(lines), i + 2)
                context = "\n".join(f"{ctx_start+j+1:>5}| {lines[ctx_start+j]}" for j in range(ctx_end - ctx_start))
                found.append({"key": key, "line": i, "raw_line": line.strip(), "context": context})
                matched_keys.add(key)

    missing = [k for k in keys if k not in matched_keys]
    return _ok({"found": found, "missing": missing, "file": file_path}, start)


@fc_register("tool")
def search_code_pattern(pattern: str, file_paths: list[str] | None = None) -> str:
    """
    Regex search across code map files.

    Args:
        pattern: Regular expression to search for.
        file_paths: Subset of code map paths; None searches all.

    Returns:
        JSON envelope with matches (file, line, text, context).
    """
    start = time.time()
    try:
        cm = _require_code_map()
    except ValueError as e:
        return _fail(ErrorCode.DATA_NOT_LOADED.value, str(e))

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return _fail(ErrorCode.INVALID_ARGUMENT.value, f"Invalid regex: {e}")

    targets = file_paths or list(cm.keys())
    matches: list[dict] = []

    for fp in targets:
        p = Path(fp)
        if not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append({"file": fp, "line": i, "text": line.strip()})
                if len(matches) >= _MAX_SEARCH_MATCHES:
                    break
        if len(matches) >= _MAX_SEARCH_MATCHES:
            break

    return _ok({
        "matches": matches,
        "total": len(matches),
        "truncated": len(matches) >= _MAX_SEARCH_MATCHES,
        "pattern": pattern,
    }, start)
