"""Trace perspective agent: per-step retrieval/rerank chain analysis."""
from __future__ import annotations
from typing import Any
from evo.agents.base import BaseAnalysisAgent

_TRACE_TOOLS = [
    "export_case_evidence", "get_case_detail", "list_cases_ranked",
    "compare_cases", "get_cluster_summary", "list_cluster_exemplars",
    "summarize_metrics", "cluster_per_step", "analyze_step_flow",
    "get_step_flow_analysis",
]

_SYSTEM_PROMPT = """\
你是 RAG 检索链分析专家。你的任务是按 pipeline 步骤顺序分析检索/重排链的问题。

## 工作流
1. **整体理解**: 阅读初始信息中的 pipeline 结构和异常摘要，
   识别哪些步骤的特征异常 (如 output_gt_hit_rate 低、ids_dropped 高、
   judge_context_recall 低)。
2. **跨步流动分析**: 用 get_step_flow_analysis 查看 case 在步骤间的聚类流动:
   - divergence: 上一步的同一簇在下一步散为多簇 → 该步引入不确定性
   - convergence: 不同簇收敛 → 该步有筛选/归一化效果
   - 关注 critical_steps 列表
3. **聚类探索**: 用 get_cluster_summary(step_key=...) 查看单步聚类的特征偏移。
4. **典型 case 深挖**: 选 2-3 个典型 case 调 export_case_evidence，
   按 pipeline 顺序逐步检查:
   - 每步的 input/output ID 传递 (id_pass_through_rate)
   - 每步对 GT 的命中率 (output_gt_hit_rate)
   - judge_context_recall / judge_doc_recall (检索质量评价)
   - 哪一步开始丢失正确文档
5. **因果链分析**: 用 compare_cases 对比好/差 case，判断:
   - 上游 Retriever 召回不足是否传导到下游 Reranker
   - Reranker 是否反而丢弃了正确结果
6. **形成假设**: 对每步给出 diagnosis 和 severity，标注因果关系。

## 约束
- 按 pipeline 顺序分析，不要跳步。
- 区分 "本步问题" 和 "上游传导"。
- 每个结论必须有工具调用获得的证据支撑。"""


class TracePerspectiveAgent(BaseAnalysisAgent):
    _task_instruction = "请按工作流主动使用工具探索数据，完成检索链分析后输出最终结论。"
    _perspective_name = "trace"

    def __init__(self, **kw: Any) -> None:
        super().__init__(name="trace_perspective", tool_names=_TRACE_TOOLS, **kw)

    def get_default_system_prompt(self) -> str:
        return _SYSTEM_PROMPT
