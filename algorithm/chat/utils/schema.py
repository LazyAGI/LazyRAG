from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class BaseMessage(BaseModel):
    """Single-turn conversation message."""
    model_config = ConfigDict(extra='forbid')

    role: Literal['user', 'assistant', 'system'] = Field(..., description='Message role')
    content: str = Field(..., description='Message text content')
    time: Optional[datetime] = Field(
        default=None,
        description='Message timestamp (optional; ISO8601, may include timezone)'
    )


class SessionMemory(BaseModel):
    """Confirmed entities/intents/constraints within the session."""
    model_config = ConfigDict(extra='forbid')

    topic: Optional[str] = Field(default=None, description='Current topic/task (optional)')
    entities: List[str] = Field(default_factory=list, description='List of related entities')
    time_hints: List[str] = Field(  # noqa: E501
        default_factory=list,
        description='Relative time hints (e.g. past three years, 2023Q4)',
    )
    source_scope: List[str] = Field(  # noqa: E501
        default_factory=list,
        description='Restricted information sources (e.g. official docs, specific reports)',
    )


@dataclass
class MiddleResults:
    evaluation_result: dict = field(default_factory=dict)
    raw_results: list = field(default_factory=list)
    formatted_results: list = field(default_factory=list)
    agg_results: dict = field(default_factory=dict)


@dataclass
class ToolMemory:
    nodes: list = field(default_factory=list)


@dataclass
class ToolCall:
    name: str
    input: dict
    output: Any


@dataclass
class PlanStep:
    step_id: int
    goal: str
    tool: str
    status: str = 'pending'
    raw_results: list = field(default_factory=list)
    formatted_results: list = field(default_factory=list)
    extracted_results: list = field(default_factory=list)
    inference: str = ''


@dataclass
class TaskContext:
    query: str = ''
    global_params: dict = field(default_factory=dict)
    tool_params: dict = field(default_factory=dict)
    pending_steps: List[PlanStep] = field(default_factory=list)
    executed_steps: List[PlanStep] = field(default_factory=list)
    middle_results: MiddleResults = field(default_factory=MiddleResults)
    inferences: List[str] = field(default_factory=list)
    reasoning_process_stream: List[str] = field(default_factory=list)
    answer: str = ''
