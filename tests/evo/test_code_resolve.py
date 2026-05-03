"""Tests for resolve_import semantic navigation tool."""

from __future__ import annotations

import sys
import traceback
from dataclasses import replace
from typing import Callable

from evo.runtime.code_config import CodeAccessConfig, ReadScope, SubjectIndex
from evo.runtime.config import load_config
from evo.runtime.session import create_session, session_scope
from evo.tools import register_all


def _h(name: str) -> None:
    print(f"\n=== {name} ===")


def _session(scope: ReadScope):
    cfg = load_config()
    return create_session(replace(
        cfg, code_access=CodeAccessConfig(
            code_map={}, read_scope=scope, subject_index=SubjectIndex(),
        ),
    ))


def test_resolve_module() -> None:
    _h("resolve_import('json') -> module file readable=true via package scope")
    register_all()
    from evo.tools.code_resolve import resolve_import
    sess = _session(ReadScope(third_party_packages=("json",)))
    with session_scope(sess):
        r = resolve_import(symbol="json")
    assert r.ok
    assert r.data["kind"] == "module"
    assert r.data["readable"] is True
    print(f"  -> {r.data['file']}:{r.data['line']}")


def test_resolve_class() -> None:
    _h("resolve_import('json.JSONDecoder') -> class with line>1")
    register_all()
    from evo.tools.code_resolve import resolve_import
    sess = _session(ReadScope(third_party_packages=("json",)))
    with session_scope(sess):
        r = resolve_import(symbol="json.JSONDecoder")
    assert r.ok
    assert r.data["kind"] == "class"
    assert r.data["line"] > 1
    print(f"  -> line={r.data['line']}, sig={r.data['signature']}")


def test_resolve_function() -> None:
    _h("resolve_import('json.dumps') -> function with signature")
    register_all()
    from evo.tools.code_resolve import resolve_import
    sess = _session(ReadScope(third_party_packages=("json",)))
    with session_scope(sess):
        r = resolve_import(symbol="json.dumps")
    assert r.ok
    assert r.data["kind"] == "function"
    assert "obj" in r.data["signature"] or "(" in r.data["signature"]
    print("  -> OK")


def test_resolve_unknown_returns_failure() -> None:
    _h("resolve_import on unknown symbol returns failure")
    register_all()
    from evo.tools.code_resolve import resolve_import
    sess = _session(ReadScope(third_party_packages=("json",)))
    with session_scope(sess):
        r = resolve_import(symbol="this_module_definitely_does_not_exist_xyz")
    assert not r.ok
    assert "import" in r.error.message.lower() or "no source" in r.error.message.lower()
    print("  -> OK")


def test_resolve_marks_unreadable_outside_scope() -> None:
    _h("resolve_import marks readable=false when symbol outside read_scope")
    register_all()
    from evo.tools.code_resolve import resolve_import
    sess = _session(ReadScope())
    with session_scope(sess):
        r = resolve_import(symbol="json.dumps")
    assert r.ok
    assert r.data["readable"] is False
    print(f"  -> reason={r.data['scope_reason']}")


def _run(tests: list[Callable[[], None]]) -> int:
    failures = 0
    for t in tests:
        try:
            t()
        except Exception:
            failures += 1
            print(f"FAILED: {t.__name__}")
            traceback.print_exc(limit=6)
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


def main() -> int:
    return _run([
        test_resolve_module,
        test_resolve_class,
        test_resolve_function,
        test_resolve_unknown_returns_failure,
        test_resolve_marks_unreadable_outside_scope,
    ])


if __name__ == "__main__":
    sys.exit(main())
