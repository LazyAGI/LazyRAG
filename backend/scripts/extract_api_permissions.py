#!/usr/bin/env python3
"""
Static analysis: extract (method, path) -> permission_required from FastAPI apps (core, auth-service).
Run at deploy time; writes api_permissions.json for auth-service and Kong.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def extract_from_file(filepath: Path) -> list[dict]:
    """Parse a Python file and yield {method, path, permissions} for protected routes."""
    text = filepath.read_text(encoding="utf-8")
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
                    if dec.func.id == "permission_required":
                        perms = []
                        for arg in dec.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                perms.append(arg.value)
                        if perms:
                            required_perms = set(perms)
                elif isinstance(dec.func, ast.Attribute):
                    # app.get, app.post, etc.
                    if getattr(dec.func.value, "id", None) in ("app", "router") and dec.args:
                        path_arg = dec.args[0]
                        if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
                            path = _normalize_path(path_arg.value)
                            method = (dec.func.attr or "GET").upper()
                            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                                method = "GET"

        if required_perms is not None and path is not None and method is not None:
            entries.append({
                "method": method,
                "path": path,
                "permissions": sorted(required_perms),
            })

    return entries


def collect_py_files(root: Path, exclude_dirs: set[str]) -> list[Path]:
    """Recursively find .py files under root, skipping dirs in exclude_dirs."""
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            rel = path.relative_to(root)
            parts = rel.parts
            if exclude_dirs and parts and parts[0] in exclude_dirs:
                continue
            out.append(path)
        except ValueError:
            continue
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract API permission_required from FastAPI apps")
    parser.add_argument("--output", "-o", type=Path, help="Output JSON path")
    parser.add_argument("--exclude", type=str, default="", help="Comma-separated subdir names to exclude when scanning (e.g. scripts,core)")
    parser.add_argument("sources", nargs="*", type=Path, help="Source directories to scan (e.g. /app/core /app)")
    args = parser.parse_args()

    exclude = {s.strip() for s in args.exclude.split(",") if s.strip()}

    if args.sources and args.output is not None:
        source_dirs = args.sources
        out_path = args.output
    elif len(args.sources) >= 2 and args.output is None:
        source_dirs = args.sources[:-1]
        out_path = args.sources[-1]
    elif not args.sources or (args.output is None and len(args.sources) < 2):
        # Default: backend/core and backend/auth-service, output to backend/auth-service/api_permissions.json
        base = Path(__file__).resolve().parent.parent
        source_dirs = [base / "core", base / "auth-service"]
        out_path = base / "auth-service" / "api_permissions.json"
        exclude = exclude or {"scripts", "core"}

    all_entries: list[dict] = []
    for src_dir in source_dirs:
        src_dir = src_dir.resolve()
        if not src_dir.is_dir():
            print(f"Warning: skip (not a directory): {src_dir}", file=sys.stderr)
            continue
        for py_file in collect_py_files(src_dir, exclude):
            try:
                all_entries.extend(extract_from_file(py_file))
            except Exception as e:
                print(f"Warning: skip {py_file}: {e}", file=sys.stderr)

    # Deduplicate by (method, path); last wins
    by_key: dict[tuple[str, str], dict] = {}
    for e in all_entries:
        by_key[(e["method"], e["path"])] = e
    result = list(by_key.values())
    result.sort(key=lambda x: (x["method"], x["path"]))

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(result)} API permission entries to {out_path}")


if __name__ == "__main__":
    main()
