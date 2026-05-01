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
    time_hints: List[str] = Field(default_factory=list, description='Relative time hints (e.g. past three years, 2023Q4)')  # noqa: E501
    source_scope: List[str] = Field(default_factory=list, description='Restricted information sources (e.g. official docs, specific reports)')  # noqa: E501


class ToolCall(BaseModel):
    """Tool call record."""
    tool_name: str
    arguments: dict
    result: Optional[Any] = None


class ToolMemory(BaseModel):
    """Tool call memory."""
    tool_calls: List[ToolCall] = Field(default_factory=list)


class PlanStep(BaseModel):
    """Single step in a plan."""
    step_id: int
    description: str
    status: str = 'pending'
    result: Optional[str] = None


@dataclass
class MiddleResults:
    """Intermediate results container."""
    retrieved_nodes: list = field(default_factory=list)
    reranked_nodes: list = field(default_factory=list)
    context_str: str = ''


@dataclass
class TaskContext:
    """Task execution context."""
    query: str = ''
    session_id: str = ''
    plan: List[PlanStep] = field(default_factory=list)
    middle_results: MiddleResults = field(default_factory=MiddleResults)
    inferences: List[str] = field(default_factory=list)
    reasoning_process_stream: List[str] = field(default_factory=list)
    answer: str = ''
