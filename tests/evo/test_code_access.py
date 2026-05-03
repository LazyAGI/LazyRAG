"""Tests for code_config / read_scope / refactored code tools."""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Callable

from evo.runtime.code_config import (
    CodeAccessConfig, ReadScope, SubjectIndex, StepSource, load_code_access,
)
from evo.runtime.config import load_config
from evo.runtime.read_scope import is_readable, resolve_in_scope
from evo.runtime.session import create_session, session_scope
from evo.tools import register_all


def _h(name: str) -> None:
    print(f"\n=== {name} ===")


def _scoped_session(read_scope: ReadScope, code_map: dict[str, str] | None = None,
                    subject: SubjectIndex | None = None):
    cfg = load_config()
    new = replace(
        cfg,
        code_access=CodeAccessConfig(
            code_map=dict(code_map or {}), read_scope=read_scope,
            subject_index=subject or SubjectIndex(),
        ),
    )
    return create_session(new)


def test_load_code_access_parses_multi_block() -> None:
    _h("load_code_access parses code_map / read_scope / subject_index")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        f = root / "x.py"
        f.write_text("x = 1\n")
        cm_file = root / "code_map.json"
        cm_file.write_text(json.dumps({
            "code_map": {str(f): "x"},
            "read_scope": {
                "project_roots": [str(root)],
                "third_party_packages": ["json"],
            },
            "subject_index": {
                "subject_entry": str(f),
                "step_to_source": {"S1": {"file": "x.py", "line": 1, "symbol": "x"}},
                "symbol_hints": {"x": "demo"},
            },
        }))
        ca = load_code_access(cm_file)
    assert ca.code_map == {str(f): "x"}
    assert root in ca.read_scope.project_roots
    assert "json" in ca.read_scope.third_party_packages
    assert ca.subject_index.subject_entry == f.resolve()
    assert ca.subject_index.step_to_source["S1"].symbol == "x"
    assert ca.subject_index.symbol_hints == {"x": "demo"}
    print("  -> OK")


def test_is_readable_project_and_excludes() -> None:
    _h("is_readable: project_roots allow; exclude_globs deny; .venv blocked by default")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        ok_file = root / "a.py"
        ok_file.write_text("a=1\n")
        venv = root / ".venv" / "lib" / "x.py"
        venv.parent.mkdir(parents=True)
        venv.write_text("y=1\n")
        scope = ReadScope(project_roots=(root,))
        good, _ = is_readable(ok_file, scope)
        bad, why = is_readable(venv, scope)
        assert good
        assert not bad and ".venv" in why
    print("  -> OK")


def test_third_party_package_overrides_excludes() -> None:
    _h("third_party_packages allows reading even under .venv (excluded by default)")
    scope = ReadScope(third_party_packages=("json",))
    import json as json_mod
    src = json_mod.__file__
    ok, why = is_readable(src, scope)
    assert ok, (src, why)
    assert why.startswith("package:json")
    print("  -> OK")


def test_resolve_in_scope_raises_outside() -> None:
    _h("resolve_in_scope raises PermissionError outside scope")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        outside = root.parent / "outside.py"
        try:
            outside.write_text("x=1\n")
            scope = ReadScope(project_roots=(root,))
            try:
                resolve_in_scope(outside, scope)
            except PermissionError:
                pass
            else:
                raise AssertionError("expected PermissionError")
        finally:
            if outside.exists():
                outside.unlink()
    print("  -> OK")


def test_read_source_file_validates_via_read_scope() -> None:
    _h("read_source_file uses read_scope (NOT code_map) for permission")
    register_all()
    from evo.tools.code import read_source_file
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        f = root / "demo.py"
        f.write_text("print('hi')\n")
        session = _scoped_session(ReadScope(project_roots=(root,)))
        with session_scope(session):
            r1 = read_source_file(file_path=str(f))
            r2 = read_source_file(file_path="/etc/passwd")
        assert r1.ok and "print" in r1.data["content"]
        assert not r2.ok
    print("  -> OK")


def test_list_subject_index_tool() -> None:
    _h("list_subject_index returns subject_entry + step_to_source + symbol_hints")
    register_all()
    from evo.tools.code import list_subject_index
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        entry = root / "mock.py"
        entry.write_text("retriever = 1\n")
        si = SubjectIndex(
            subject_entry=entry,
            step_to_source={"R1": StepSource(file="mock.py", line=1, symbol="retriever")},
            symbol_hints={"retriever": "demo"},
        )
        session = _scoped_session(ReadScope(project_roots=(root,)), subject=si)
        with session_scope(session):
            r = list_subject_index()
    assert r.ok
    assert r.data["subject_entry"].endswith("mock.py")
    assert r.data["step_to_source"]["R1"]["line"] == 1
    assert r.data["symbol_hints"] == {"retriever": "demo"}
    print("  -> OK")


def test_search_code_pattern_scope_modes() -> None:
    _h("search_code_pattern: scope='project' / 'package'")
    register_all()
    from evo.tools.code import search_code_pattern
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        (root / "a.py").write_text("def needle():\n    pass\n")
        (root / "b.txt").write_text("needle\n")
        session = _scoped_session(
            ReadScope(project_roots=(root,), third_party_packages=("json",)),
        )
        with session_scope(session):
            proj = search_code_pattern(pattern=r"\bneedle\b", scope="project")
            pkg = search_code_pattern(pattern=r"\bJSONDecodeError\b",
                                       scope="package", package="json")
    assert proj.ok and proj.data["total"] >= 1
    assert any("a.py" in m["file"] for m in proj.data["matches"])
    assert pkg.ok and pkg.data["total"] >= 1
    print("  -> OK")


def _run(tests: list[Callable[[], None]]) -> int:
    failures = 0
    for t in tests:
        try:
            t()
        except Exception:
            failures += 1
            print(f"FAILED: {t.__name__}")
            traceback.print_exc(limit=8)
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


def main() -> int:
    return _run([
        test_load_code_access_parses_multi_block,
        test_is_readable_project_and_excludes,
        test_third_party_package_overrides_excludes,
        test_resolve_in_scope_raises_outside,
        test_read_source_file_validates_via_read_scope,
        test_list_subject_index_tool,
        test_search_code_pattern_scope_modes,
    ])


if __name__ == "__main__":
    sys.exit(main())
