"""JudgeEval perspective agent: generation quality + eval-data trust."""
from __future__ import annotations
from typing import Any
from evo.agents.base import BaseAnalysisAgent

_JUDGE_TOOLS = [
    "summarize_metrics", "correlate_metrics", "list_bad_cases",
    "list_cases_ranked", "export_case_evidence", "get_case_detail",
    "compare_cases", "get_cluster_summary", "get_step_flow_analysis",
]

_SYSTEM_PROMPT = """\
你是 RAG 生成质量与评测数据分析专家。

## 工作流
1. **宏观扫描**: 先调 summarize_metrics 看整体指标分布，找到哪些指标异常。
   注意新增的 judge 侧特征: judge_faithfulness, judge_answer_correctness,
   judge_key_hit_rate (生成步骤), judge_context_recall, judge_doc_recall (检索步骤)。
2. **相关性分析**: 调 correlate_metrics 看指标间关联，判断问题是否由上游传导。
3. **跨步流动**: 用 get_step_flow_analysis 查看 case 在步骤间如何流动，
   是否存在检索差→生成差的传导链。
4. **定位坏例**: 用 list_bad_cases 或 list_cases_ranked 找到最差的 case。
5. **深挖典型 case**: 对 2-3 个最差 case 调 export_case_evidence，检查:
   - 生成答案 vs GT 答案的差异
   - key_points 命中情况
   - faithfulness 与 context_recall 的关系
6. **对比分析**: 用 compare_cases 对比一个好 case 和一个差 case。
7. **形成假设**: 区分三类问题:
   - 模型生成质量问题 (faithfulness 低但 context_recall 高)
   - 评测数据/标注问题 (gt_answer 不合理)
   - 上游检索传导 (context_recall/doc_recall 低导致生成差)

## 约束
- 每个结论必须有工具调用获得的证据支撑。
- 重点关注: 是生成问题还是标注问题?"""


class JudgeEvalPerspectiveAgent(BaseAnalysisAgent):
    _perspective_name = "judge_eval"

    def __init__(self, **kw: Any) -> None:
        super().__init__(name="judge_eval_perspective", tool_names=_JUDGE_TOOLS, **kw)

    def get_default_system_prompt(self) -> str:
        return _SYSTEM_PROMPT
