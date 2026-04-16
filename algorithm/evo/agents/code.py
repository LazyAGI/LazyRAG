"""Code perspective agent: locate parameters/logic causing issues."""
from __future__ import annotations
from typing import Any
from evo.agents.base import BaseAnalysisAgent

_CODE_TOOLS = [
    "list_code_map", "parse_code_structure", "read_source_file",
    "extract_config_values", "search_code_pattern", "export_case_evidence",
]

_SYSTEM_PROMPT = """\
你是 RAG 系统代码分析专家。你的任务是将步骤级特征异常定位到具体的代码参数和逻辑。

## 工作流
1. **理解异常**: 阅读初始信息中的步骤特征异常摘要。
2. **代码地图**: 调 list_code_map 查看可用文件，根据描述判断哪些与异常步骤相关。
3. **结构探索**: 对相关文件调 parse_code_structure，找到关键类/函数/配置变量。
4. **参数定位**: 用 extract_config_values 搜索关键参数:
   - 召回不足 → 搜索 topk, similarity_threshold, chunk_size
   - 重排异常 → 搜索 rerank, score_threshold, top_n
   - 生成问题 → 搜索 temperature, max_tokens, prompt
5. **代码精读**: 用 read_source_file 精确读取参数上下文 (±20行)。
6. **运行时验证**: 可选用 export_case_evidence 验证代码参数与运行时行为的一致性。

## 约束
- 不要一次读取整个文件。先 parse_code_structure 了解结构，再精确读取。
- 优先关注可调参数 (topk / threshold / temperature 等) 作为根因。
- 引用具体文件路径和行号。"""


class CodePerspectiveAgent(BaseAnalysisAgent):
    _task_heading = "步骤特征异常摘要"
    _task_instruction = (
        "请按工作流主动使用工具探索代码，将特征异常定位到具体参数/逻辑，"
        "完成后输出最终结论。"
    )
    _max_case_ids = 10
    _perspective_name = "code"

    def __init__(self, **kw: Any) -> None:
        super().__init__(name="code_perspective", tool_names=_CODE_TOOLS, **kw)

    def get_default_system_prompt(self) -> str:
        return _SYSTEM_PROMPT
