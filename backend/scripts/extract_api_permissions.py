#!/usr/bin/env python3
"""
Extract (method, path) -> permissions from:
- Python: FastAPI apps using @permission_required (auth-service).
- Go: handleAPI(mux, method, path, []string{...}, handler) at route registration (core).
Run at deploy time; writes api_permissions.json for auth-service and Kong.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

import yaml


def _normalize_path(path: str) -> str:
    return path.rstrip('/') or '/'


def _get_router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            continue
        if value.func.id != 'APIRouter':
            continue
        prefix = ''
        for kw in value.keywords:
            if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                prefix = kw.value.value
                break
        prefixes[target_name] = _normalize_path(prefix) if prefix else ''
    return prefixes


def _join_paths(prefix: str, path: str) -> str:
    prefix = prefix.rstrip('/')
    path = path.rstrip('/')
    if not prefix and not path:
        return '/'
    if not prefix:
        return path or '/'
    if not path or path == '/':
        return prefix or '/'
    return f'{prefix}{path if path.startswith("/") else "/" + path}'


def _extract_module_api_prefix(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == '_API_PREFIX':
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return _normalize_path(node.value.value)
    return ''


def extract_from_py_file(filepath: Path) -> list[dict]:
    """Parse a Python file for @permission_required + app/router method decorators."""
    text = filepath.read_text(encoding='utf-8')
    tree = ast.parse(text)
    router_prefixes = _get_router_prefixes(tree)
    module_api_prefix = _extract_module_api_prefix(tree)
    if not module_api_prefix and 'auth-service' in filepath.parts:
        module_api_prefix = '/api/authservice'
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
                    router_name = getattr(dec.func.value, 'id', None)
                    if router_name in ('app', 'router') or router_name in router_prefixes:
                        if dec.args:
                            path_arg = dec.args[0]
                            if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
                                route_path = _normalize_path(path_arg.value)
                                prefix = router_prefixes.get(router_name, '')
                                local_path = _normalize_path(_join_paths(prefix, route_path))
                                path = _normalize_path(_join_paths(module_api_prefix, local_path))
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
    api_prefix = '/api/core' if 'core' in filepath.parts else ''
    for m in _GO_HANDLE_API_RE.finditer(text):
        method = (m.group(1) or 'GET').upper()
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
            method = 'GET'
        raw_path = _normalize_path(m.group(2) or '/')
        path = _normalize_path(_join_paths(api_prefix, raw_path))
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


def _extract_permission_codes(entries: list[dict]) -> list[str]:
    codes: set[str] = set()
    for item in entries:
        perms = item.get('permissions') or []
        for p in perms:
            s = str(p or '').strip()
            if s:
                codes.add(s)
    return sorted(codes)


def _read_permission_groups_yaml(path: Path) -> tuple[str, dict]:
    """
    Read permission_groups.yaml returning (leading_comment_block, data_dict).
    Leading comments are preserved (best-effort).
    """
    if not path.exists():
        return '', {}
    text = path.read_text(encoding='utf-8')
    comment_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith('#') or not line.strip():
            comment_lines.append(line)
            continue
        break
    try:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    comment_block = '\n'.join(comment_lines).rstrip() + ('\n' if comment_lines else '')
    return comment_block, data


def _sync_permission_groups_yaml(path: Path, used_codes: list[str]) -> None:
    """
    Sync permission_groups.yaml.permission_groups from used_codes (full overwrite).
    - Overwrites permission_groups with the full, de-duplicated set of used codes.
    - Does NOT delete/modify any DB data (bootstrap is additive).
    - Preserves leading comment block best-effort.
    - Keeps other YAML keys as-is (e.g. default_user_role_permissions) if present.
    """
    header, data = _read_permission_groups_yaml(path)
    merged = sorted(set(used_codes))

    out: dict = dict(data)
    out['permission_groups'] = merged
    if 'default_user_role_permissions' not in out:
        out['default_user_role_permissions'] = []

    body = yaml.safe_dump(out, sort_keys=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Extract API permissions from Python (FastAPI @permission_required) and Go (APIRoutePermissions)'
    )
    parser.add_argument('--output', '-o', type=Path, help='Output JSON path')
    parser.add_argument(
        '--sync-permission-groups',
        type=Path,
        default=None,
        help='Optional permission_groups.yaml path to sync (adds missing codes only)',
    )
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

    used_codes = _extract_permission_codes(result)
    if args.sync_permission_groups is not None:
        pg_path = args.sync_permission_groups.resolve()
    else:
        # Default: auth-service/permission_groups.yaml next to the default output location
        pg_path = out_path.parent / 'permission_groups.yaml'
    _sync_permission_groups_yaml(pg_path, used_codes)
    print(f'Synced {len(used_codes)} permission codes to {pg_path}')


if __name__ == '__main__':
    main()
