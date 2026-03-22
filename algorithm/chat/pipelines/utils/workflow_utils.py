from dataclasses import dataclass, field
from typing import Any, List


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
    goal: str                 # 这一轮想搞清楚什么
    tool: str
    status: str = 'pending'
    raw_results: list = field(default_factory=list)  # 原始结果类型，包含metadata，方便回溯内容来源
    formatted_results: list = field(default_factory=list)  # 结构化的结果，str，用于中间推理和答案生成
    extracted_results: list = field(default_factory=list)  # 过滤过的结构化结果， 对应更新raw_results
    inference: str = ''


@dataclass
class ReasoningProcess:
    tools: list[ToolCall] = field(default_factory=list)


@dataclass
class TaskContext:
    query: str = ''
    global_params: dict = field(default_factory=dict)
    tool_params: dict = field(default_factory=dict)
    pending_steps: List[PlanStep] = field(default_factory=list)
    executed_steps: List[PlanStep] = field(default_factory=list)
    middle_results: MiddleResults = field(default_factory=MiddleResults)
    inferences: List[str] = field(default_factory=list)
    reasoning_process_stream: List[str] = field(default_factory=list)  # 推理过程，用于流式输出
    answer: str = ''


def tool_schema_to_string(
    tool_schema: dict,
    include_params: bool = True
) -> str:
    lines = []

    for tool_name, tool_info in tool_schema.items():
        lines.append(f'TOOL NAME: {tool_name}')

        # description
        desc = tool_info.get('description')
        if desc:
            lines.append('DESCRIPTION:')
            for sent in desc.split('. '):
                sent = sent.strip()
                if sent:
                    lines.append(f"- {sent.rstrip('.')}.")

        # parameters
        if include_params:
            params = tool_info.get('parameters', {})
            if params:
                lines.append('PARAMETERS:')
                for param_name, param_info in params.items():
                    p_type = param_info.get('type', 'Any')
                    p_desc = param_info.get('des', '')
                    if p_desc:
                        lines.append(
                            f'- {param_name}: {p_type} — {p_desc}'
                        )
                    else:
                        lines.append(
                            f'- {param_name}: {p_type}'
                        )

    return '\n'.join(lines).strip()
