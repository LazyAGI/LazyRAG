"""Chair agent: merge perspective reports + synthesize guidance via tool-using ReAct."""

from __future__ import annotations

import json
import logging
from typing import Any

from evo.agents.base import BaseAnalysisAgent
from evo.agents.parsing import extract_json_object, OUTPUT_SCHEMA

_log = logging.getLogger("evo.chair")

_CHAIR_TOOLS = [
    "export_case_evidence",
    "get_case_detail",
    "summarize_metrics",
    "compare_cases",
    "get_cluster_summary",
    "get_step_flow_analysis",
]

_SYSTEM_PROMPT = """\
你是 RAG 系统诊断主席。你已经收到了各视角 Agent 的结构化分析结果（已经预合并）。

你的任务:
1. 审查预合并的 per_step_diagnosis，用工具验证关键结论:
   - 对最严重的 step，调 export_case_evidence 抽查 1-2 个触发 case
   - 用 get_step_flow_analysis 确认因果链方向
   - 用 summarize_metrics 核实全局指标是否支持诊断
2. 对有疑问的诊断，用 compare_cases 对比好/差 case 补充证据。
3. 基于验证后的诊断，撰写 guidance（详细 markdown 改进指导），包含:
   - 按优先级排列的改进建议
   - 每个建议的具体参数/策略调整
   - 验证方法

最终输出严格 JSON (不要 markdown 围栏):
{
  "per_step_diagnosis": [...],  // 验证后的诊断（可修正预合并结果）
  "actions": [...],             // 优先级排序的行动项
  "guidance": "...",            // markdown 格式的详细改进指导
  "summary": "..."             // 一句话总结
}"""


def _merge_perspectives(perspectives: list[dict], pipeline: list[str]) -> dict[str, Any]:
    """Mechanically merge perspective reports into a single diagnosis.

    Deterministic: no LLM needed. Dedup by step_key, keep highest confidence.
    """
    all_diag: dict[str, dict[str, Any]] = {}
    for report in perspectives:
        for d in report.get("per_step_diagnosis", []):
            sk = d.get("step_key", "unknown")
            existing = all_diag.get(sk)
            if existing is None:
                all_diag[sk] = {**d, "_sources": [report.get("perspective", "?")]}
            else:
                _SEV_ORDER = {"CRITICAL": 3, "MEDIUM": 2, "LOW": 1, "OK": 0}
                new_sev = _SEV_ORDER.get(d.get("severity", "OK"), 0)
                old_sev = _SEV_ORDER.get(existing.get("severity", "OK"), 0)
                if new_sev > old_sev:
                    all_diag[sk] = {**d, "_sources": existing["_sources"] + [report.get("perspective", "?")]}
                else:
                    existing["_sources"].append(report.get("perspective", "?"))

    # Sort by pipeline order
    ordered = []
    for sk in pipeline:
        if sk in all_diag:
            ordered.append(all_diag.pop(sk))
    ordered.extend(all_diag.values())

    all_hyps: list[dict] = []
    for report in perspectives:
        for h in report.get("hypotheses", []):
            all_hyps.append({**h, "perspective": report.get("perspective", "?")})
    all_hyps.sort(key=lambda h: -h.get("confidence", 0))

    # Dedup hypotheses by stage + hypothesis text
    seen: set[str] = set()
    deduped_hyps = []
    for h in all_hyps:
        key = f"{h.get('stage', '')}:{h.get('hypothesis', '')[:80]}"
        if key not in seen:
            seen.add(key)
            deduped_hyps.append(h)

    all_effects: list[dict] = []
    for report in perspectives:
        all_effects.extend(report.get("interaction_effects", []))

    return {
        "per_step_diagnosis": ordered,
        "hypotheses": deduped_hyps[:15],
        "interaction_effects": all_effects,
    }


class ChairAgent(BaseAnalysisAgent):

    def __init__(self, **kw: Any) -> None:
        super().__init__(name="chair", tool_names=_CHAIR_TOOLS, use_cache=False, **kw)

    def get_default_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def synthesize(self, perspectives: list[dict], pipeline: list[str],
                   flow_skeleton: list[dict], metadata: dict[str, Any]) -> dict[str, Any]:
        merged = _merge_perspectives(perspectives, pipeline)
        _log.info("Merged: %d per_step_diagnosis, %d hypotheses",
                  len(merged["per_step_diagnosis"]), len(merged["hypotheses"]))

        if not merged["per_step_diagnosis"] and not merged["hypotheses"]:
            _log.warning("No structured data from perspectives, skipping chair verification")
            summaries = [r.get("summary", "") for r in perspectives if r.get("summary")]
            return {
                "per_step_diagnosis": [],
                "actions": [],
                "guidance": "\n\n".join(summaries) or "No analysis available.",
                "summary": summaries[0][:200] if summaries else "No analysis available.",
            }

        briefing = json.dumps({
            "pipeline": pipeline,
            "flow_skeleton": flow_skeleton,
            "merged_diagnosis": merged,
            "metadata": metadata,
        }, ensure_ascii=False, indent=2)

        task = (
            f"## 预合并的分析结果\n{briefing}\n\n"
            "请用工具验证关键诊断，然后输出最终 JSON 结果。\n\n"
            f"## 输出格式\n{OUTPUT_SCHEMA}"
        )

        raw = self._run_governed_llm(
            lambda: self._run_react_loop(task, max_rounds=6),
            cache_key=f"chair:{hash(briefing) & 0xFFFFFFFF:08x}",
            log_preview="chair_synthesize",
        )

        result = extract_json_object(raw)
        if result and (result.get("per_step_diagnosis") or result.get("actions") or result.get("guidance")):
            _log.info("Chair produced: %d per_step_diagnosis, %d actions, guidance=%d chars",
                      len(result.get("per_step_diagnosis", [])),
                      len(result.get("actions", [])),
                      len(result.get("guidance", "")))
            return result

        _log.warning("Chair LLM output unusable, falling back to merged data")
        actions = []
        for h in merged["hypotheses"][:10]:
            actions.append({
                "stage": h.get("stage", "unknown"),
                "hypothesis": h.get("hypothesis", ""),
                "severity": "MEDIUM",
                "confidence": h.get("confidence", 0.5),
                "evidence_finding": "; ".join(h.get("evidence_refs", [])),
                "suggested_changes": h.get("reasoning", ""),
            })

        return {
            "per_step_diagnosis": merged["per_step_diagnosis"],
            "actions": actions,
            "guidance": self._build_fallback_guidance(merged),
            "summary": f"Identified {len(merged['per_step_diagnosis'])} step issues, {len(actions)} action items.",
        }

    @staticmethod
    def _build_fallback_guidance(merged: dict) -> str:
        lines = ["# RAG 系统诊断报告\n"]
        for i, d in enumerate(merged["per_step_diagnosis"]):
            lines.append(f"## {i+1}. [{d.get('severity', 'MEDIUM')}] {d.get('step_key', 'unknown')}")
            lines.append(f"- **问题**: {d.get('issue', 'N/A')}")
            lines.append(f"- **证据**: {d.get('evidence', 'N/A')}")
            lines.append(f"- **建议**: {d.get('suggested_fix', 'N/A')}")
            lines.append("")
        if merged.get("hypotheses"):
            lines.append("## 假设列表\n")
            for h in merged["hypotheses"][:10]:
                lines.append(f"- **[{h.get('stage', '?')}]** {h.get('hypothesis', '')} (confidence={h.get('confidence', 0):.2f})")
        return "\n".join(lines)
