from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class OpenCodeOptions(TypedDict, total=False):
    model: str
    agent: str
    variant: str
    binary: str
    timeout_s: int


class ExecutePayload(TypedDict, total=False):
    repo_path: str
    base_ref: str
    task_plan: Dict[str, Any]
    code_context: Dict[str, Any]
    opencode: OpenCodeOptions


class ModifyResult(TypedDict):
    diff: str
    files_changed: List[str]
    change_summary: str


class ErrorPayload(TypedDict):
    code: str
    message: str
    details: Dict[str, Any]


class AdapterOutcome(TypedDict):
    status: str
    result: Optional[ModifyResult]
    error: Optional[ErrorPayload]
    artifacts_dir: str
