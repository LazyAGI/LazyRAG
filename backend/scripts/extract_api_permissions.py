#!/usr/bin/env python3
"""
Extract (method, path) -> permissions from:
- Python: FastAPI apps using @permission_required (auth-service).
- Go: handleAPI(mux, method, path, []string{...}, handler) at route registration (core).
Run at deploy time; writes api_permissions.json for auth-service and Kong.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


def _normalize_path(path: str) -> str:
    return path.rstrip('/') or '/'


def extract_from_py_file(filepath: Path) -> list[dict]:
    """Parse a Python file for @permission_required + app.get/post(path)."""
    text = filepath.read_text(encoding='utf-8')
    tree = ast.parse(text)
    entries = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        required_perms: set[str] | None = None
        method: str | None = None
        path: str | None = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    if dec.func.id == 'permission_required':
                        perms = []
                        for arg in dec.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                perms.append(arg.value)
                        if perms:
                            required_perms = set(perms)
                elif isinstance(dec.func, ast.Attribute):
                    if getattr(dec.func.value, 'id', None) in ('app', 'router') and dec.args:
                        path_arg = dec.args[0]
                        if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
                            path = _normalize_path(path_arg.value)
                            method = (dec.func.attr or 'GET').upper()
                            if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
                                method = 'GET'
        if required_perms is not None and path is not None and method is not None:
            entries.append({'method': method, 'path': path, 'permissions': sorted(required_perms)})
    return entries


# handleAPI(mux, "GET", "/api/hello", []string{"user.read"}, handler) — per-route permission at registration
_GO_HANDLE_API_RE = re.compile(
    r'handleAPI\s*\(\s*[^,]+,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*\[\]string\{(.*?)\}\s*,',  # noqa: Q000
    re.DOTALL,
)


def _parse_go_permissions(s: str) -> list[str]:
    return [p.strip().strip(chr(34)) for p in s.split(',') if p.strip()]


def extract_from_go_file(filepath: Path) -> list[dict]:
    """Parse a Go file for handleAPI(mux, method, path, []string{...}, ...) calls."""
    text = filepath.read_text(encoding='utf-8')
    entries = []
    for m in _GO_HANDLE_API_RE.finditer(text):
        method = (m.group(1) or 'GET').upper()
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
            method = 'GET'
        path = _normalize_path(m.group(2) or '/')
        perms = _parse_go_permissions(m.group(3))
        if perms:
            entries.append({'method': method, 'path': path, 'permissions': sorted(perms)})
    return entries


def collect_files(root: Path, exclude_dirs: set[str], ext: str) -> list[Path]:
    """Recursively find files with given extension under root, skipping exclude_dirs."""
    out: list[Path] = []
    for path in root.rglob(f'*{ext}'):
        if path.name.startswith('_'):
            continue
        try:
            rel = path.relative_to(root)
            if exclude_dirs and rel.parts and rel.parts[0] in exclude_dirs:
                continue
            out.append(path)
        except ValueError:
            continue
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Extract API permissions from Python (FastAPI @permission_required) and Go (APIRoutePermissions)'
    )
    parser.add_argument('--output', '-o', type=Path, help='Output JSON path')
    parser.add_argument(
        '--exclude', type=str, default='',
        help='Comma-separated subdir names to exclude (e.g. scripts,core,vendor)',
    )
    parser.add_argument('sources', nargs='*', type=Path, help='Source directories (e.g. /app/core /app)')
    args = parser.parse_args()

    exclude = {s.strip() for s in args.exclude.split(',') if s.strip()}

    if args.sources and args.output is not None:
        source_dirs = args.sources
        out_path = args.output
    elif len(args.sources) >= 2 and args.output is None:
        source_dirs = args.sources[:-1]
        out_path = args.sources[-1]
    else:
        base = Path(__file__).resolve().parent.parent
        source_dirs = [base / 'core', base / 'auth-service']
        out_path = base / 'auth-service' / 'api_permissions.json'
        exclude = exclude or {'scripts', 'core', 'vendor'}

    all_entries: list[dict] = []
    for src_dir in source_dirs:
        src_dir = src_dir.resolve()
        if not src_dir.is_dir():
            print(f'Warning: skip (not a directory): {src_dir}', file=sys.stderr)
            continue
        for py_file in collect_files(src_dir, exclude, '.py'):
            try:
                all_entries.extend(extract_from_py_file(py_file))
            except Exception as e:
                print(f'Warning: skip {py_file}: {e}', file=sys.stderr)
        for go_file in collect_files(src_dir, exclude, '.go'):
            try:
                all_entries.extend(extract_from_go_file(go_file))
            except Exception as e:
                print(f'Warning: skip {go_file}: {e}', file=sys.stderr)

    by_key: dict[tuple[str, str], dict] = {}
    for e in all_entries:
        by_key[(e['method'], e['path'])] = e
    result = sorted(by_key.values(), key=lambda x: (x['method'], x['path']))

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {len(result)} API permission entries to {out_path}')


if __name__ == '__main__':
    main()
