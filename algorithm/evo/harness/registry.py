from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import threading
import time
import traceback
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Iterable

from evo.domain.tool_result import ErrorCode, ToolResult

_log = logging.getLogger("evo.tools.registry")

ToolFn = Callable[..., ToolResult[Any]]
LLMFn = Callable[..., str]
Middleware = Callable[["ToolSpec", dict[str, Any], ToolResult[Any]], ToolResult[Any]]


Summarizer = Callable[[ToolResult[Any]], str]


@dataclass
class ToolSpec:
    name: str
    fn: ToolFn
    doc: str
    signature: inspect.Signature
    tags: list[str] = field(default_factory=list)
    lazyllm_group: str = "tool"
    summarizer: Summarizer | None = None

    def describe(self) -> str:
        params: list[str] = []
        for pname, param in self.signature.parameters.items():
            p = pname
            if param.default is not inspect.Parameter.empty:
                p += f"={param.default!r}"
            params.append(p)
        head = (self.doc or "").strip().split("\n\n")[0]
        return f"- **{self.name}**({', '.join(params)}): {head}"

    def summarize_result(self, result: ToolResult[Any], *, max_chars: int = 200) -> str:
        """One-line summary of ``result`` for sliding-window history.

        Uses tool-specific summarizer when registered; falls back to a
        compact JSON preview. Always trimmed to ``max_chars``.
        """
        if not result.ok:
            err = (result.error.message if result.error else "error")[:max_chars]
            return f"FAIL {err}"
        try:
            text = (self.summarizer or _default_summarizer)(result)
        except Exception as exc:
            text = f"<summarizer error: {exc}>"
        return text[:max_chars]


class ToolRegistry:
    def __init__(self, *, discovery_package: str = "evo.tools") -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._middlewares: list[Middleware] = []
        self._discovery_package = discovery_package
        self._discovered = False
        self._discovery_lock = threading.Lock()

    def add_middleware(self, fn: Middleware) -> None:
        self._middlewares.append(fn)

    def clear_middlewares(self) -> None:
        self._middlewares.clear()

    @property
    def middlewares(self) -> list[Middleware]:
        return list(self._middlewares)

    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        if spec.name in self._specs and not replace:
            _log.debug("Tool %s already registered; skipping", spec.name)
            return
        self._specs[spec.name] = spec

    def _ensure_discovered(self) -> None:
        if self._discovered:
            return
        with self._discovery_lock:
            if self._discovered:
                return
            try:
                _discover_package(self._discovery_package)
            except Exception as exc:  # pragma: no cover
                _log.warning("Tool auto-discovery failed: %s", exc)
            finally:
                self._discovered = True

    def get(self, name: str) -> ToolSpec:
        spec = self._specs.get(name)
        if spec is None:
            self._ensure_discovered()
            spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"Unknown tool: {name}. Known: {sorted(self._specs)}")
        return spec

    def __contains__(self, name: str) -> bool:  # pragma: no cover
        if name in self._specs:
            return True
        self._ensure_discovered()
        return name in self._specs

    def names(self) -> list[str]:
        self._ensure_discovered()
        return sorted(self._specs)

    def all(self) -> list[ToolSpec]:
        self._ensure_discovered()
        return [self._specs[n] for n in sorted(self._specs)]

    def subset(self, names: Iterable[str]) -> list[ToolSpec]:
        return [self.get(n) for n in names]


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def _wrap(fn: ToolFn, name: str) -> ToolFn:
    @wraps(fn)
    def _inner(**kwargs: Any) -> ToolResult[Any]:
        t0 = time.time()
        try:
            result = fn(**kwargs)
        except Exception as exc:
            _log.exception("Tool %s crashed", name)
            result = ToolResult.failure(
                name, ErrorCode.INTERNAL_ERROR,
                f"{type(exc).__name__}: {exc}",
                details={"traceback": traceback.format_exc(limit=5)},
                latency_ms=(time.time() - t0) * 1000,
            )
        if not isinstance(result, ToolResult):
            result = ToolResult.failure(
                name, ErrorCode.INTERNAL_ERROR,
                f"Tool {name} returned {type(result).__name__}, expected ToolResult",
                latency_ms=(time.time() - t0) * 1000,
            )
        if not result.tool:
            result.tool = name
        if result.latency_ms == 0.0:
            result.latency_ms = (time.time() - t0) * 1000

        if result.ok and result.handle is None:
            from evo.runtime.session import get_current_session
            sess = get_current_session()
            if sess is not None and sess.handle_store is not None:
                result.handle = sess.handle_store.append(name, kwargs, result.data)

        spec = _registry._specs.get(name)
        if spec is not None and _registry._middlewares:
            for mw in _registry._middlewares:
                try:
                    result = mw(spec, kwargs, result)
                except Exception as exc:
                    _log.warning("Middleware %s on %s raised: %s", mw, name, exc)
        return result
    return _inner


def _default_summarizer(result: ToolResult[Any]) -> str:
    import json
    data = result.data
    if isinstance(data, dict):
        keys = sorted(data.keys())[:6]
        return f"keys={keys}"
    if isinstance(data, list):
        return f"list of {len(data)} items"
    try:
        return json.dumps(data, ensure_ascii=False)[:200]
    except Exception:
        return f"<{type(data).__name__}>"


def tool(
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    lazyllm_group: str = "tool",
    llm_exposed: bool = True,
    summarizer: Summarizer | None = None,
) -> Callable[[ToolFn], ToolFn]:
    def decorator(fn: ToolFn) -> ToolFn:
        tool_name = name or fn.__name__
        wrapped = _wrap(fn, tool_name)
        spec = ToolSpec(
            name=tool_name,
            fn=wrapped,
            doc=inspect.getdoc(fn) or "",
            signature=inspect.signature(fn),
            tags=list(tags or []),
            lazyllm_group=lazyllm_group,
            summarizer=summarizer,
        )
        _registry.register(spec, replace=True)
        if llm_exposed:
            _try_register_lazyllm(wrapped, tool_name, lazyllm_group)
        return wrapped
    return decorator


def _try_register_lazyllm(wrapped: ToolFn, name: str, group: str) -> None:
    try:
        from lazyllm.tools import fc_register  # type: ignore
    except Exception:
        return

    def _call(**kwargs: Any) -> str:
        return wrapped(**kwargs).to_json()

    _call.__name__ = name
    _call.__qualname__ = name
    _call.__doc__ = wrapped.__doc__
    try:
        fc_register(group)(_call)
    except Exception as exc:
        _log.debug("lazyllm registration for %s skipped: %s", name, exc)


def get_llm_callable(name: str) -> LLMFn:
    spec = _registry.get(name)

    def _call(**kwargs: Any) -> str:
        return spec.fn(**kwargs).to_json()

    _call.__name__ = name
    _call.__doc__ = spec.doc
    _call.__signature__ = spec.signature  # type: ignore[attr-defined]
    return _call


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------

def _discover_package(package: str) -> None:
    mod = importlib.import_module(package)
    if not hasattr(mod, "__path__"):
        return
    for info in pkgutil.walk_packages(mod.__path__, prefix=f"{package}."):
        if info.name.endswith(".registry"):
            continue
        try:
            importlib.import_module(info.name)
        except Exception as exc:  # pragma: no cover - surface, but never crash
            _log.warning("Skipping %s during tool discovery: %s", info.name, exc)


def discover(package: str = "evo.tools") -> list[str]:
    _discover_package(package)
    _registry._discovered = True
    return sorted(_registry._specs)
