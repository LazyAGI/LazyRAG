"""Single I/O tool. The only place inside the codebase that writes files."""

from __future__ import annotations

from typing import Any

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.session import get_current_session
from evo.utils import safe_under


@tool(tags=["io"])
def write_artifact(relpath: str, content: str) -> ToolResult[dict[str, Any]]:
    """Write *content* to ``output_dir/relpath`` (sandboxed via ``safe_under``).

    Args:
        relpath: Path relative to the session's ``config.output_dir``.
        content: Text content to write (UTF-8).

    Returns:
        ``{"path": str, "size_bytes": int}``. Does NOT mutate Session state.
        The caller (Harness) is responsible for recording the artifact via
        ``session.add_artifact(...)`` if it wants to track the path.
    """
    if not relpath:
        return ToolResult.failure("write_artifact", ErrorCode.INVALID_ARGUMENT,
                                  "relpath is required.")
    if content is None:
        return ToolResult.failure("write_artifact", ErrorCode.INVALID_ARGUMENT,
                                  "content is required (use empty string for empty files).")
    session = get_current_session()
    if session is None:
        return ToolResult.failure("write_artifact", ErrorCode.DATA_NOT_LOADED,
                                  "No active session.")
    try:
        path = safe_under(session.config.output_dir, relpath)
    except ValueError as exc:
        return ToolResult.failure("write_artifact", ErrorCode.INVALID_ARGUMENT, str(exc))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ToolResult.success("write_artifact", {
        "path": str(path),
        "size_bytes": path.stat().st_size,
    })
