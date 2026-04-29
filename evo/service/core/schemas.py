from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    num_cases: int | None = Field(default=None, ge=1, le=200)


class EvalCreate(BaseModel):
    thread_id: str
    dataset_id: str | None = None
    eval_id: str | None = None
    target_chat_url: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def _exactly_one_target(self) -> 'EvalCreate':
        if bool(self.dataset_id) == bool(self.eval_id):
            raise ValueError('provide exactly one of dataset_id or eval_id')
        return self


class AbtestCreate(BaseModel):
    thread_id: str
    apply_id: str
    baseline_eval_id: str
    dataset_id: str
    apply_worktree: str | None = None
    target_chat_url: str | None = None
    candidate_chat_id: str | None = None
    eval_options: dict[str, Any] = Field(default_factory=dict)
    policy: VerdictPolicyModel = Field(default_factory=VerdictPolicyModel)


class ThreadFlowStatus(BaseModel):
    thread_id: str
    status: Literal['not_found', 'running', 'ended']
    active_task_ids: list[str] = Field(default_factory=list)
    latest_abtest_id: str | None = None
    latest_abtest_status: str | None = None
    report_ready: bool = False
