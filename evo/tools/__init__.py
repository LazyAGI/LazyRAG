from __future__ import annotations
from evo.harness.registry import discover, get_registry
_discovered: list[str] | None = None
def register_all() -> list[str]:
    global _discovered
    if _discovered is not None:
        return _discovered
    _discovered = discover('evo.tools')
    return _discovered
def tool_names() -> list[str]:
    if _discovered is None:
        register_all()
    return get_registry().names()
