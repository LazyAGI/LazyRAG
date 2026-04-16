"""Shared utilities for all tool modules."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from evo.domain.schemas import (
    ToolSuccess, ToolFailure, ToolError, ToolMeta, ErrorCode,
)
from evo.runtime.session import get_current_session


def safe_under(base: Path, user_path: str) -> Path:
    """Resolve *user_path* under *base*, rejecting traversal."""
    base = base.resolve()
    if ".." in Path(user_path).parts:
        raise ValueError(f"Path traversal rejected: {user_path}")
    resolved = (base / user_path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(f"Path escapes base directory: {user_path}")
    return resolved


def _ok(data: Any, start: float) -> str:
    """Wrap *data* in ToolSuccess with latency metadata."""
    return ToolSuccess(
        data=data, meta=ToolMeta(latency_ms=(time.time() - start) * 1000)
    ).to_json()


def _fail(code: str, message: str) -> str:
    """Return ToolFailure JSON envelope."""
    return ToolFailure(error=ToolError(code=code, message=message)).to_json()
