from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VerdictPolicyModel(BaseModel):
    primary_metric: str = 'answer_correctness'
    eps: float = 0.01
    p_value: float = 0.05
    guard_metrics: tuple[str, ...] = ('doc_recall', 'context_recall')
    guard_eps: float = 0.02


class RunCreate(BaseModel):
    thread_id: str | None = None
    eval_id: str | None = None
    badcase_limit: int | None = None
    score_field: str | None = None


class ApplyCreate(BaseModel):
    thread_id: str | None = None
    report_id: str | None = None


class DatasetGenCreate(BaseModel):
    thread_id: str | None = None
    kb_id: str
    algo_id: str = 'general_algo'
    eval_name: str | None = None


class EvalCreate(BaseModel):
    thread_id: str
    dataset_id: str | None = None
    eval_id: str | None = None
    target_chat_url: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class MergeCreate(BaseModel):
    thread_id: str | None = None
    apply_id: str
    strategy: Literal['merge-commit', 'squash', 'fast-forward'] = 'merge-commit'
    auto_deploy: bool = False


class DeployCreate(BaseModel):
    thread_id: str | None = None
    merge_id: str
    adapter: str = 'local'
    version: str = 'latest'
    role: str = 'production'
    keep_old: bool = True


class AbtestCreate(BaseModel):
    thread_id: str
    apply_id: str
    baseline_eval_id: str
    dataset_id: str
    apply_worktree: str | None = None
    target_chat_url: str | None = None
    eval_options: dict[str, Any] = Field(default_factory=dict)
    policy: VerdictPolicyModel = Field(default_factory=VerdictPolicyModel)
