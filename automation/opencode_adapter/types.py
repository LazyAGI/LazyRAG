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


class ValidationCheckResult(TypedDict):
    name: str
    status: str
    command: str
    returncode: Optional[int]
    stdout: str
    stderr: str
    reason: str


class ValidationResult(TypedDict):
    status: str
    checks: List[ValidationCheckResult]
    summary: str


class TaskExecutionResult(TypedDict):
    task_id: str
    execution_task_id: str
    module: str
    status: str
    modify_result: Optional[AdapterOutcome]
    validation_result: ValidationResult
    remaining_risks: List[str]


class ReportSummary(TypedDict):
    total_tasks: int
    succeeded: int
    partial: int
    failed: int
    blocked: int
    no_change: int
    files_changed: List[str]
    remaining_risks: List[str]


class ReportOutcome(TypedDict):
    status: str
    report_id: str
    task_results: List[TaskExecutionResult]
    summary: ReportSummary
    artifacts_dir: str
