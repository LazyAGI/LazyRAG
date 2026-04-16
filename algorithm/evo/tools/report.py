"""
Reporting tools (fc_register group ``report``).

Implementation contract (README.md Phase E.6):
    - ``create_diagnosis_report``: validate input against ``DiagnosisReport`` model; include
      AB-test strategy blocks; stable schema versioning field.
    - ``format_report_for_display``: support at least ``markdown`` and ``json``; optional ``html``.
    - ``save_report``: enforce ``safe_under(session.output_dir, ...)``; reject ``..``; return saved path.

All functions return JSON strings (envelope) except ``format_report_for_display`` may return
raw markdown/text inside envelope ``data`` under a ``text`` key—document the chosen convention.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from lazyllm.tools import fc_register
from evo.domain.schemas import (
    ToolSuccess, ToolFailure, ToolError, ToolMeta,
    ErrorCode, DiagnosisReport, KeyFinding, ActionItem, AbTestPolicy,
    Severity,
)
from evo.runtime.session import get_current_session
from evo.tools._common import safe_under


def _coerce_changes(val: Any) -> dict[str, dict[str, Any]]:
    if isinstance(val, dict):
        return {str(k): v if isinstance(v, dict) else {"value": v} for k, v in val.items()}
    if isinstance(val, str) and val.strip():
        return {"note": {"text": val}}
    return {}


@fc_register("tool")
def create_diagnosis_report(analysis_data: str) -> str:
    """
    Build the canonical diagnosis report from pipeline JSON
    (actions, per_step_diagnosis, global_step_analysis, guidance, metadata.total_cases, …).
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None:
            return ToolFailure(
                error=ToolError(
                    code=ErrorCode.DATA_NOT_LOADED.value,
                    message="No active session."
                )
            ).to_json()
        
        try:
            data = json.loads(analysis_data)
        except json.JSONDecodeError as e:
            return ToolFailure(
                error=ToolError(
                    code=ErrorCode.INVALID_ARGUMENT.value,
                    message=f"Invalid JSON input: {str(e)}"
                )
            ).to_json()
        
        if "data" in data:
            data = data["data"]
        
        timestamp = datetime.now()
        report_id = f"report_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        meta_in = data.get("metadata") or {}
        total_cases = int(meta_in.get("total_cases", 0))
        metadata = {
            "report_id": report_id,
            "created_at": timestamp.isoformat(),
            "schema_version": "1.0.0",
            "run_id": session.run_id,
            "total_cases_analyzed": total_cases,
        }

        _SEV_MAP = {
            "CRITICAL": Severity.CRITICAL,
            "MEDIUM": Severity.MEDIUM,
            "LOW": Severity.LOW,
            "INFO": Severity.INFO,
            "OK": Severity.INFO,
        }

        actions = [a for a in (data.get("actions") or []) if isinstance(a, dict)]
        per_step_all = [p for p in (data.get("per_step_diagnosis") or []) if isinstance(p, dict)]

        key_findings: dict[str, KeyFinding] = {}
        action_list: dict[str, ActionItem] = {}

        for i, action in enumerate(actions[:10]):
            raw_sev = str(action.get("severity", "MEDIUM")).upper()
            severity = _SEV_MAP.get(raw_sev, Severity.MEDIUM)
            n_cases = len(action.get("trigger_cases") or [])
            key_findings[f"finding_{i}"] = KeyFinding(
                severity=severity,
                field=str(action.get("stage", "unknown")),
                behavior=action.get("symptoms", "") or action.get("hypothesis", ""),
                range=f"{n_cases} cases",
                count=n_cases,
                action=str(action.get("rationale", "")),
            )
            action_list[f"action_{i}"] = ActionItem(
                priority=int(action.get("priority", i + 1)),
                symptoms=action.get("symptoms", "") or action.get("hypothesis", ""),
                trigger_metric=str(action.get("verification_metric", "answer_correctness")),
                trigger_cases=(action.get("trigger_cases") or [])[:5],
                hypothesis=str(action.get("hypothesis", "")),
                evidence_basis_type=str(action.get("evidence_basis_type", "agent")),
                evidence_finding=str(action.get("evidence_finding", "")),
                evidence_confidence=float(action.get("confidence", 0.5)),
                changes=_coerce_changes(action.get("suggested_changes")),
                validation_cases=(action.get("trigger_cases") or [])[:5],
                owner_team_suggestion=action.get("owner_team_suggestion"),
                verification_metric=action.get("verification_metric"),
                rollback_metric=action.get("rollback_metric"),
            )

        if not key_findings and per_step_all:
            for i, step in enumerate(per_step_all[:10]):
                raw_sev = str(step.get("severity", "MEDIUM")).upper()
                severity = _SEV_MAP.get(raw_sev, Severity.MEDIUM)
                sk = str(step.get("step_key") or f"step_{i}")
                issue = str(step.get("issue", ""))
                evidence = str(step.get("evidence", ""))
                fix = str(step.get("suggested_fix", ""))
                root = str(step.get("root_cause", ""))
                hyp = f"{root}: {issue}".strip(": ").strip() if (root or issue) else sk
                key_findings[f"finding_{i}"] = KeyFinding(
                    severity=severity,
                    field=sk,
                    behavior=issue or evidence or sk,
                    range="per-step",
                    count=1,
                    action=fix,
                )
                action_list[f"action_{i}"] = ActionItem(
                    priority=i + 1,
                    symptoms=issue or sk,
                    trigger_metric=sk,
                    trigger_cases=[],
                    hypothesis=hyp,
                    evidence_basis_type="agent",
                    evidence_finding=evidence,
                    evidence_confidence=0.5,
                    changes=_coerce_changes(fix),
                    validation_cases=[],
                )

        ab_data = data.get("abtest_strategy") or {}
        abtest_strategy = AbTestPolicy(
            success_criteria=ab_data.get("success_criteria", {
                "correctness_improvement": 0.1,
                "recall_improvement": 0.15,
            }),
            early_stop=ab_data.get("early_stop", {
                "threshold": 0.05,
                "min_samples": 100,
            }),
            control_group_size=ab_data.get("control_group_size", 1000),
            experiment_group_size=ab_data.get("experiment_group_size", 1000),
        )

        top_issue: str | None = None
        if actions:
            top_issue = actions[0].get("hypothesis") or actions[0].get("symptoms")
        elif per_step_all:
            top_issue = per_step_all[0].get("issue") or per_step_all[0].get("step_key")

        summary = {
            "total_findings": len(key_findings),
            "total_actions": len(action_list),
            "top_issue": top_issue,
            "severity_distribution": {
                "critical": sum(1 for f in key_findings.values() if f.severity == Severity.CRITICAL),
                "medium": sum(1 for f in key_findings.values() if f.severity == Severity.MEDIUM),
                "low": sum(1 for f in key_findings.values() if f.severity == Severity.LOW),
                "info": sum(1 for f in key_findings.values() if f.severity == Severity.INFO),
            },
        }

        gsa = data.get("global_step_analysis")
        global_step_analysis = gsa if isinstance(gsa, dict) else {}
        cc_raw = data.get("code_correlations")
        if isinstance(cc_raw, dict):
            code_corr = cc_raw.get("correlations")
        elif isinstance(cc_raw, list):
            code_corr = cc_raw
        else:
            code_corr = None
        mp_raw = data.get("modification_plan")
        if isinstance(mp_raw, dict):
            mod_plan = mp_raw.get("modification_plan")
        elif isinstance(mp_raw, list):
            mod_plan = mp_raw
        else:
            mod_plan = None

        report = DiagnosisReport(
            report_id=report_id,
            metadata=metadata,
            summary=summary,
            key_findings=key_findings,
            expected_edit={},
            action_list=action_list,
            abtest_strategy=abtest_strategy,
            guidance=str(data.get("guidance", "") or ""),
            per_step_diagnosis=per_step_all,
            global_step_analysis=global_step_analysis,
            chair_summary=str(data.get("chair_summary", "") or ""),
            chair_parse_failed=bool(data.get("chair_parse_failed")),
            interaction_effects=data.get("interaction_effects"),
            cross_case_patterns=data.get("cross_case_patterns"),
            causal_chains=data.get("causal_chains"),
            code_correlations=code_corr,
            modification_plan=mod_plan,
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return ToolSuccess(
            data={
                "report_id": report.report_id,
                "metadata": report.metadata,
                "summary": report.summary,
                "key_findings": {
                    k: {
                        "severity": v.severity.value,
                        "field": v.field,
                        "behavior": v.behavior,
                        "range": v.range,
                        "count": v.count,
                        "action": v.action
                    }
                    for k, v in report.key_findings.items()
                },
                "action_list": {
                    k: {
                        "priority": v.priority,
                        "symptoms": v.symptoms,
                        "trigger_metric": v.trigger_metric,
                        "trigger_cases": v.trigger_cases,
                        "hypothesis": v.hypothesis,
                        "evidence_basis_type": v.evidence_basis_type,
                        "evidence_finding": v.evidence_finding,
                        "evidence_confidence": v.evidence_confidence,
                        "changes": v.changes,
                        "validation_cases": v.validation_cases,
                        "owner_team_suggestion": v.owner_team_suggestion,
                        "verification_metric": v.verification_metric,
                        "rollback_metric": v.rollback_metric
                    }
                    for k, v in report.action_list.items()
                },
                "abtest_strategy": {
                    "success_criteria": report.abtest_strategy.success_criteria,
                    "early_stop": report.abtest_strategy.early_stop,
                    "control_group_size": report.abtest_strategy.control_group_size,
                    "experiment_group_size": report.abtest_strategy.experiment_group_size
                },
                "interaction_effects": report.interaction_effects or [],
                "cross_case_patterns": report.cross_case_patterns or [],
                "causal_chains": report.causal_chains or {},
                "code_correlations": report.code_correlations or [],
                "modification_plan": report.modification_plan or [],
                "guidance": report.guidance,
                "per_step_diagnosis": report.per_step_diagnosis,
                "global_step_analysis": report.global_step_analysis,
                "chair_summary": report.chair_summary,
                "chair_parse_failed": report.chair_parse_failed,
            },
            meta=ToolMeta(latency_ms=latency_ms)
        ).to_json()
        
    except Exception as e:
        return ToolFailure(
            error=ToolError(
                code=ErrorCode.INTERNAL_ERROR.value,
                message=f"Failed to create diagnosis report: {str(e)}",
                details={"exception_type": type(e).__name__}
            )
        ).to_json()


# ---------------------------------------------------------------------------
# Report rendering helpers
# ---------------------------------------------------------------------------

_HEATMAP_BLOCKS = " ░▒▓█"


def _val_to_block(val: float, lo: float = 0.0, hi: float = 1.0) -> str:
    if val is None:
        return "?"
    frac = max(0.0, min(1.0, (val - lo) / (hi - lo))) if hi > lo else 0.5
    idx = int(frac * (len(_HEATMAP_BLOCKS) - 1))
    return _HEATMAP_BLOCKS[idx]


def _append_metrics_heatmap(lines: list[str], report: dict) -> None:
    """Append an ASCII metrics heatmap for all analyzed cases (from key_findings context)."""
    cross = report.get("cross_case_patterns", {})
    patterns = cross.get("patterns", cross) if isinstance(cross, dict) else cross
    if not isinstance(patterns, list):
        patterns = []

    case_metrics: dict[str, dict[str, float]] = {}
    for pat in patterns:
        for cid in pat.get("affected_case_ids", []):
            if cid not in case_metrics:
                case_metrics[cid] = {}
        feats = pat.get("distinguishing_features", {})
        for cid in pat.get("affected_case_ids", []):
            for fname, finfo in feats.items():
                if isinstance(finfo, dict) and "value" in finfo:
                    case_metrics.setdefault(cid, {})[fname] = finfo["value"]

    if not case_metrics:
        return

    metric_names = ["context_recall", "doc_recall", "faithfulness", "answer_correctness"]
    short_names = ["ctx_rec", "doc_rec", "faith", "ans_cor"]

    has_data = False
    for cm in case_metrics.values():
        if any(m in cm for m in metric_names):
            has_data = True
            break
    if not has_data:
        return

    lines.append("## 指标热力图")
    lines.append("")
    header = f"{'Case':<14}" + "".join(f"{s:>10}" for s in short_names)
    lines.append(f"```")
    lines.append(header)
    lines.append("-" * len(header))
    for cid in sorted(case_metrics.keys()):
        cm = case_metrics[cid]
        row = f"{cid:<14}"
        for m in metric_names:
            v = cm.get(m)
            if v is not None:
                block = _val_to_block(v)
                row += f"{block} {v:.2f}   "
            else:
                row += "   N/A    "
        lines.append(row)
    lines.append(f"```")
    lines.append(f"*刻度: {_HEATMAP_BLOCKS} (0.0 → 1.0)*")
    lines.append("")


def _append_causal_flowchart(lines: list[str], chain_data: dict, case_id: str) -> None:
    """Append an ASCII pipeline flowchart showing impact at each stage."""
    chain = chain_data.get("chain", [])
    if not chain:
        return

    lines.append(f"**流程图 ({case_id})**:")
    lines.append("```")

    for i, step in enumerate(chain):
        stage = step.get("stage", "?")
        impact = step.get("impact_score", 0)
        bar_len = int(impact * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        arrow = " → " if i < len(chain) - 1 else "   "

        lines.append(f"  [{stage:<16}] |{bar}| {impact:.2f}{arrow}")

    bottleneck = chain_data.get("bottleneck_stage", "")
    if bottleneck:
        lines.append(f"  ⚠ 瓶颈: {bottleneck}")
    lines.append("```")
    lines.append("")


def _append_incremental_delta(lines: list[str], report: dict) -> None:
    """Append incremental comparison section if delta data is present."""
    delta = report.get("incremental_delta")
    if not delta:
        return

    lines.append("## 增量分析 (vs 基线)")
    lines.append("")

    baseline_id = delta.get("baseline_report_id", "N/A")
    lines.append(f"- **基线报告**: {baseline_id}")
    lines.append("")

    metric_deltas = delta.get("metric_deltas", {})
    if metric_deltas:
        lines.append("### 指标变化")
        lines.append("")
        lines.append("| 指标 | 基线 | 当前 | 变化 | 方向 |")
        lines.append("|------|------|------|------|------|")
        for mname, md in metric_deltas.items():
            before = md.get("before", "?")
            after = md.get("after", "?")
            delta_val = md.get("delta", 0)
            direction = md.get("direction", "unchanged")
            symbol = "↑" if direction == "improved" else ("↓" if direction == "degraded" else "→")
            lines.append(
                f"| {mname} | {before:.3f} | {after:.3f} | "
                f"{delta_val:+.3f} | {symbol} {direction} |"
            )
        lines.append("")

    new_issues = delta.get("new_issues", [])
    if new_issues:
        lines.append("### 新增问题 (回归)")
        lines.append("")
        for issue in new_issues:
            lines.append(f"- **{issue.get('hypothesis', '?')}** [{issue.get('stage', '?')}] (置信度 {issue.get('confidence', 0):.0%})")
        lines.append("")

    resolved = delta.get("resolved_issues", [])
    if resolved:
        lines.append("### 已解决问题")
        lines.append("")
        for issue in resolved:
            lines.append(f"- ~~{issue.get('hypothesis', '?')}~~ [{issue.get('stage', '?')}]")
        lines.append("")

    persistent = delta.get("persistent_issues", [])
    if persistent:
        lines.append("### 持续问题")
        lines.append("")
        for issue in persistent:
            trend = issue.get("trend", "unchanged")
            symbol = "↑" if trend == "improving" else ("↓" if trend == "worsening" else "→")
            lines.append(f"- {symbol} {issue.get('hypothesis', '?')} [{issue.get('stage', '?')}]")
        lines.append("")


_ROLE_SECTIONS: dict[str, set[str]] = {
    "developer": set(),  # empty = keep everything
    "ops": {
        "## 报告信息",
        "## 执行摘要",
        "## Chair 输出",
        "## 主席摘要",
        "## 改进指导",
        "## 逐步诊断",
        "## 步骤特征聚合",
        "## 快速修复建议 Top 3",
        "## 指标热力图",
        "## 行动建议",
        "## 因果链分析",
        "## AB测试策略",
        "## 增量分析",
    },
    "product": {
        "## 报告信息",
        "## 执行摘要",
        "## Chair 输出",
        "## 主席摘要",
        "## 改进指导",
        "## 逐步诊断",
        "## 步骤特征聚合",
        "## 快速修复建议 Top 3",
        "## 指标热力图",
        "## 关键发现",
        "## 跨Case模式分析",
        "## 查询语义聚类",
        "## 增量分析",
    },
}


def _apply_role_filter(full_md: str, role: str) -> str:
    """Keep only sections relevant to *role*. 'developer' keeps everything."""
    allowed = _ROLE_SECTIONS.get(role)
    if not allowed:
        return full_md

    lines = full_md.split("\n")
    result: list[str] = []
    include = True
    for line in lines:
        if line.startswith("## "):
            heading = line.split("\n")[0].rstrip()
            include = any(heading.startswith(s) for s in allowed) or heading == "# RAG系统诊断报告"
        if line.startswith("# ") and not line.startswith("## "):
            include = True
        if include:
            result.append(line)

    return "\n".join(result)


@fc_register("tool")
def format_report_for_display(report_json: str, format_type: str = "markdown", role_perspective: str = "developer") -> str:
    """
    Render a report JSON into human-readable form.

    Args:
        report_json: Output of ``create_diagnosis_report`` (or compatible).
        format_type: ``markdown`` | ``json`` | ``text``.
        role_perspective: ``developer`` (full detail) | ``ops`` (metrics + actions) |
            ``product`` (summary + patterns only).

    Returns:
        JSON envelope with:
        - text: Formatted string (markdown/json/text)
        - format: The format type used
    """
    start_time = time.time()
    
    valid_formats = ("markdown", "json", "text")
    if format_type not in valid_formats:
        return ToolFailure(
            error=ToolError(
                code=ErrorCode.INVALID_ARGUMENT.value,
                message=f"format_type must be one of {valid_formats}, got '{format_type}'"
            )
        ).to_json()
    
    try:
        try:
            report = json.loads(report_json)
        except json.JSONDecodeError as e:
            return ToolFailure(
                error=ToolError(
                    code=ErrorCode.INVALID_ARGUMENT.value,
                    message=f"Invalid JSON input: {str(e)}"
                )
            ).to_json()
        
        if "data" in report:
            report = report["data"]
        
        if format_type == "json":
            latency_ms = (time.time() - start_time) * 1000
            return ToolSuccess(
                data={
                    "text": json.dumps(report, ensure_ascii=False, indent=2),
                    "format": "json"
                },
                meta=ToolMeta(latency_ms=latency_ms)
            ).to_json()
        
        if format_type == "text":
            lines = []
            lines.append("=" * 60)
            lines.append("RAG系统诊断报告")
            lines.append("=" * 60)
            lines.append("")
            
            metadata = report.get("metadata", {})
            lines.append(f"报告ID: {metadata.get('report_id', 'N/A')}")
            lines.append(f"生成时间: {metadata.get('created_at', 'N/A')}")
            lines.append(f"分析案例数: {metadata.get('total_cases_analyzed', 0)}")
            lines.append("")
            
            summary = report.get("summary", {})
            lines.append("执行摘要")
            lines.append("-" * 40)
            lines.append(f"关键发现数: {summary.get('total_findings', 0)}")
            lines.append(f"行动建议数: {summary.get('total_actions', 0)}")
            if summary.get("top_issue"):
                lines.append(f"首要问题: {summary['top_issue']}")
            lines.append("")
            
            text = "\n".join(lines)
            
            latency_ms = (time.time() - start_time) * 1000
            return ToolSuccess(
                data={"text": text, "format": "text"},
                meta=ToolMeta(latency_ms=latency_ms)
            ).to_json()
        
        if format_type == "markdown":
            lines = []
            
            metadata = report.get("metadata", {})
            lines.append(f"# RAG系统诊断报告")
            lines.append("")
            lines.append("## 报告信息")
            lines.append("")
            lines.append(f"- **报告ID**: {metadata.get('report_id', 'N/A')}")
            lines.append(f"- **生成时间**: {metadata.get('created_at', 'N/A')}")
            lines.append(f"- **分析案例数**: {metadata.get('total_cases_analyzed', 0)}")
            lines.append(f"- **Schema版本**: {metadata.get('schema_version', 'N/A')}")
            lines.append("")
            
            summary = report.get("summary", {})
            lines.append("## 执行摘要")
            lines.append("")
            sev_dist = summary.get("severity_distribution", {})
            lines.append(f"- CRITICAL: {sev_dist.get('critical', 0)}")
            lines.append(f"- MEDIUM: {sev_dist.get('medium', 0)}")
            lines.append(f"- LOW: {sev_dist.get('low', 0)}")
            if summary.get("top_issue"):
                lines.append(f"- **首要问题**: {summary['top_issue']}")
            sev_info = summary.get("severity_distribution", {}).get("info")
            if sev_info:
                lines.append(f"- **INFO/OK**: {sev_info}")
            lines.append("")

            if report.get("chair_parse_failed"):
                lines.append("## Chair 输出")
                lines.append("")
                lines.append("⚠️ Chair 返回未按严格 JSON 解析；以下为保留的摘要、逐步诊断与指导正文。")
                lines.append("")
            cs = report.get("chair_summary", "")
            if cs:
                lines.append("## 主席摘要")
                lines.append("")
                lines.append(cs)
                lines.append("")
            gd = report.get("guidance", "")
            if gd:
                lines.append("## 改进指导")
                lines.append("")
                lines.append(gd)
                lines.append("")
            psd = report.get("per_step_diagnosis") or []
            if psd:
                lines.append("## 逐步诊断")
                lines.append("")
                for row in psd:
                    if not isinstance(row, dict):
                        continue
                    sk = row.get("step_key", "?")
                    lines.append(f"### {sk}")
                    lines.append("")
                    lines.append(f"- **问题**: {row.get('issue', '')}")
                    lines.append(
                        f"- **严重度**: {row.get('severity', '')} | **根因**: {row.get('root_cause', '')}"
                    )
                    ev = row.get("evidence", "")
                    if ev:
                        evs = str(ev)
                        tail = "…" if len(evs) > 500 else ""
                        lines.append(f"- **证据**: {evs[:500]}{tail}")
                    sf = row.get("suggested_fix", "")
                    if sf:
                        lines.append(f"- **建议**: {sf}")
                    lines.append("")
            gsa = report.get("global_step_analysis") or {}
            if gsa:
                lines.append("## 步骤特征聚合")
                lines.append("")
                blob = json.dumps(gsa, ensure_ascii=False, indent=2)
                lines.append("```json")
                lines.append(blob[:12000] + ("…" if len(blob) > 12000 else ""))
                lines.append("```")
                lines.append("")

            # --- Quick fix summary (Top 3) ---
            actions_list = list(report.get("action_list", {}).values())
            actions_sorted = sorted(actions_list, key=lambda a: a.get("priority", 99))[:3]
            if actions_sorted:
                lines.append("## 快速修复建议 Top 3")
                lines.append("")
                for rank, act in enumerate(actions_sorted, 1):
                    hyp = act.get("hypothesis", "N/A")[:120]
                    stage = act.get("trigger_metric", "")
                    conf = act.get("evidence_confidence", 0)
                    cases = act.get("trigger_cases", [])
                    lines.append(f"**{rank}. {hyp}**")
                    lines.append(f"   验证指标: `{stage}` | 置信度: {conf:.0%} | 影响: {len(cases)} case(s)")
                    lines.append("")
            
            # --- Metrics heatmap (ASCII) ---
            _append_metrics_heatmap(lines, report)

            lines.append("## 关键发现")
            lines.append("")
            for finding_id, finding in report.get("key_findings", {}).items():
                lines.append(f"### {finding_id}")
                lines.append("")
                lines.append(f"- **严重程度**: {finding.get('severity', 'UNKNOWN')}")
                lines.append(f"- **问题领域**: {finding.get('field', 'N/A')}")
                lines.append(f"- **问题描述**: {finding.get('behavior', 'N/A')}")
                lines.append(f"- **影响范围**: {finding.get('range', 'N/A')}")
                lines.append(f"- **建议行动**: {finding.get('action', 'N/A')}")
                lines.append("")
            
            lines.append("## 行动建议")
            lines.append("")
            for action_id, action in report.get("action_list", {}).items():
                lines.append(f"### {action_id} (优先级: {action.get('priority', 'N/A')})")
                lines.append("")
                lines.append(f"**症状**: {action.get('symptoms', 'N/A')}")
                lines.append("")
                lines.append(f"**假设**: {action.get('hypothesis', 'N/A')}")
                lines.append("")
                lines.append(f"**触发案例**: {', '.join(action.get('trigger_cases', []))}")
                lines.append("")
                lines.append(f"**验证指标**: {action.get('verification_metric', 'N/A')}")
                lines.append("")
                lines.append(f"**回滚指标**: {action.get('rollback_metric', 'N/A')}")
                lines.append("")
                lines.append("---")
                lines.append("")
            
            # --- Interaction effects (cascade analysis) ---
            ie_list = report.get("interaction_effects", [])
            if ie_list:
                lines.append("## 交互效应分析")
                lines.append("")
                for ie in ie_list:
                    path = ie.get("path", ie.get("stages", []))
                    path_str = " → ".join(path) if path else "unknown"
                    ctype = ie.get("cascade_type") or path_str
                    cscore = ie.get("cascade_score")
                    source = ie.get("source", "unknown")

                    header = f"### {ctype}"
                    if cscore is not None:
                        header += f" (score: {cscore:.2f})"
                    lines.append(header)
                    lines.append("")
                    lines.append(f"**路径**: {path_str}")
                    lines.append("")
                    desc = ie.get("description", "")
                    if desc:
                        lines.append(f"**描述**: {desc}")
                        lines.append("")
                    evidence = ie.get("evidence", [])
                    if evidence:
                        lines.append("**证据**:")
                        if isinstance(evidence, str):
                            lines.append(f"- {evidence}")
                        elif isinstance(evidence, list):
                            for ev in evidence:
                                if isinstance(ev, str) and len(ev) > 1:
                                    lines.append(f"- {ev}")
                        lines.append("")
                    fix = ie.get("suggested_fix", "")
                    if fix:
                        lines.append(f"**建议修复**: {fix}")
                        lines.append("")
                    lines.append(f"*来源: {source}*")
                    lines.append("")
                    lines.append("---")
                    lines.append("")

            # --- Cross-case patterns ---
            cross_case = report.get("cross_case_patterns", {})
            patterns = cross_case if isinstance(cross_case, list) else cross_case.get("patterns", cross_case) if isinstance(cross_case, dict) else []
            if isinstance(patterns, dict):
                patterns = patterns.get("patterns", [])
            if patterns:
                lines.append("## 跨Case模式分析")
                lines.append("")
                for pat in patterns:
                    pid = pat.get("pattern_id", "?")
                    lines.append(f"### 模式 {pid}")
                    lines.append("")
                    lines.append(f"- **描述**: {pat.get('description', '')}")
                    lines.append(f"- **置信度**: {pat.get('confidence', 0):.0%}")
                    affected = pat.get("affected_case_ids", [])
                    lines.append(f"- **影响Case**: {', '.join(affected)}")
                    feats = pat.get("distinguishing_features", {})
                    if feats:
                        lines.append(f"- **特征**: {json.dumps(feats, ensure_ascii=False)}")
                    if pat.get("llm_description"):
                        lines.append(f"- **LLM分析**: {pat['llm_description'][:300]}")
                    lines.append("")

            # --- Anomaly detection ---
            anomalies = (
                cross_case.get("anomalies", []) if isinstance(cross_case, dict) else []
            )
            if anomalies:
                lines.append("## 异常检测")
                lines.append("")
                lines.append(f"共检测到 **{len(anomalies)}** 个异常。")
                lines.append("")
                for anom in anomalies:
                    cid = anom.get("case_id", "?")
                    atype = anom.get("anomaly_type", "unknown")
                    subtype = anom.get("subtype", "")
                    sev = anom.get("severity", "MEDIUM")
                    label = f"{atype}/{subtype}" if subtype else atype
                    lines.append(f"### {cid} [{sev}] — {label}")
                    lines.append("")
                    lines.append(f"{anom.get('explanation', '')}")
                    score = anom.get("anomaly_score")
                    if score is not None:
                        lines.append(f"- **异常分数**: {score:.3f}")
                    metrics = anom.get("metrics", {})
                    if metrics:
                        lines.append(f"- **关键指标**: {', '.join(f'{k}={v}' for k, v in metrics.items())}")
                    lines.append("")

            # --- Query semantic clustering ---
            query_groups = (
                cross_case.get("query_groups", []) if isinstance(cross_case, dict) else []
            )
            if query_groups:
                lines.append("## 查询语义聚类")
                lines.append("")
                lines.append(f"共发现 **{len(query_groups)}** 组语义相似查询。")
                lines.append("")
                for grp in query_groups:
                    gid = grp.get("group_id", "?")
                    lines.append(f"### 查询组 {gid}")
                    lines.append("")
                    lines.append(f"- **代表查询**: {grp.get('representative_query', '')[:150]}")
                    fr = grp.get("failure_rate", 0)
                    lines.append(f"- **失败率**: {fr:.0%}")
                    cases = grp.get("case_ids", [])
                    lines.append(f"- **包含Case**: {', '.join(cases)}")
                    avg = grp.get("avg_metrics", {})
                    if avg:
                        lines.append(f"- **平均指标**: {', '.join(f'{k}={v:.3f}' for k, v in avg.items())}")
                    if grp.get("description"):
                        lines.append(f"- **LLM分析**: {grp['description'][:300]}")
                    lines.append("")

            # --- Causal chains ---
            chains = report.get("causal_chains", {})
            if chains:
                lines.append("## 因果链分析")
                lines.append("")
                for cid, chain_data in chains.items():
                    if isinstance(chain_data, dict) and "error" not in chain_data:
                        lines.append(f"### {cid}")
                        lines.append("")
                        _append_causal_flowchart(lines, chain_data, cid)
                        bottleneck = chain_data.get("bottleneck_stage", "N/A")
                        lines.append(f"**瓶颈阶段**: {bottleneck}")
                        lines.append("")
                        lines.append("| 阶段 | 信息损失 | 影响 |")
                        lines.append("|------|---------|------|")
                        for step in chain_data.get("chain", []):
                            stage = step.get("stage", "?")
                            lost = step.get("information_lost", "")[:60]
                            impact = step.get("impact_score", 0)
                            lines.append(f"| {stage} | {lost} | {impact:.2f} |")
                        lines.append("")

            # --- Code correlations ---
            code_corr_data = report.get("code_correlations", {})
            if isinstance(code_corr_data, dict):
                code_corr = code_corr_data.get("correlations", [])
            elif isinstance(code_corr_data, list):
                code_corr = code_corr_data
            else:
                code_corr = []
            if code_corr:
                lines.append("## 代码关联")
                lines.append("")
                for corr in code_corr:
                    stage = corr.get("stage", corr.get("root_cause_stage", ""))
                    hypothesis = corr.get("hypothesis", "")
                    heading = f"{stage}: {hypothesis}" if stage else hypothesis
                    lines.append(f"### {heading}")
                    lines.append("")
                    for fc in corr.get("correlations", []):
                        fp = fc.get("file", "?")
                        lines.append(f"- **文件**: `{fp}` — {fc.get('description', '')}")
                        for mp in fc.get("matched_params", []):
                            lines.append(f"  - L{mp.get('line', '?')}: `{mp.get('raw', '')[:120]}`")
                    lines.append("")

            # --- Modification plan ---
            mod_plan = report.get("modification_plan", [])
            if mod_plan:
                lines.append("## 修改建议")
                lines.append("")
                for mod in mod_plan:
                    pri = mod.get("priority", "?")
                    stage = mod.get("stage", "?")
                    lines.append(f"### 优先级 {pri} — {stage}")
                    lines.append("")
                    lines.append(f"**假设**: {mod.get('hypothesis', '')}")
                    lines.append("")
                    files = mod.get("files", [])
                    if files:
                        lines.append(f"**涉及文件**: {', '.join(f'`{f}`' for f in files)}")
                        lines.append("")
                    for sc in mod.get("suggested_changes", []):
                        param = sc.get("param", "?")
                        action = sc.get("suggested_action", "")
                        risk = sc.get("risk_level", "?")
                        lines.append(f"- `{param}` (L{sc.get('line', '?')}): {action} [风险: {risk}]")
                        if sc.get("current_raw"):
                            lines.append(f"  - 当前: `{sc['current_raw'][:80]}`")
                    lines.append("")
                    vs = mod.get("verification_steps", [])
                    if vs:
                        lines.append("**验证步骤**:")
                        for v in vs:
                            lines.append(f"  {v}")
                        lines.append("")

            # --- AB test strategy ---
            abtest = report.get("abtest_strategy", {})
            lines.append("## AB测试策略")
            lines.append("")
            lines.append("### 成功标准")
            for criterion, value in abtest.get("success_criteria", {}).items():
                lines.append(f"- {criterion}: {value}")
            lines.append("")
            lines.append("### 提前停止条件")
            for criterion, value in abtest.get("early_stop", {}).items():
                lines.append(f"- {criterion}: {value}")
            lines.append("")

            # --- Incremental delta (if present) ---
            _append_incremental_delta(lines, report)

            # --- Role-based filtering ---
            text = _apply_role_filter("\n".join(lines), role_perspective)
            
            latency_ms = (time.time() - start_time) * 1000
            return ToolSuccess(
                data={"text": text, "format": "markdown", "role": role_perspective},
                meta=ToolMeta(latency_ms=latency_ms)
            ).to_json()
        
    except Exception as e:
        return ToolFailure(
            error=ToolError(
                code=ErrorCode.INTERNAL_ERROR.value,
                message=f"Failed to format report: {str(e)}",
                details={"exception_type": type(e).__name__}
            )
        ).to_json()


@fc_register("tool")
def save_report(report_json: str, output_path: str) -> str:
    """
    Persist ``report_json`` to disk inside the sandboxed output tree.

    Args:
        report_json: Report JSON string to save.
        output_path: Relative path within output directory (e.g., "reports/final.json").

    Returns:
        JSON envelope with ``saved_to`` absolute path on success.

    Error codes:
        DATA_NOT_LOADED: No active session.
        INVALID_ARGUMENT: Path traversal attempt or invalid JSON.
        IO_ERROR: File system error.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None:
            return ToolFailure(
                error=ToolError(
                    code=ErrorCode.DATA_NOT_LOADED.value,
                    message="No active session."
                )
            ).to_json()
        
        try:
            report = json.loads(report_json)
        except json.JSONDecodeError as e:
            return ToolFailure(
                error=ToolError(
                    code=ErrorCode.INVALID_ARGUMENT.value,
                    message=f"Invalid JSON input: {str(e)}"
                )
            ).to_json()
        
        output_dir = session.config.output_dir
        
        try:
            safe_path = safe_under(output_dir, output_path)
        except ValueError as e:
            return ToolFailure(
                error=ToolError(
                    code=ErrorCode.INVALID_ARGUMENT.value,
                    message=str(e)
                )
            ).to_json()
        
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        session.artifact_paths[f"report_{output_path}"] = safe_path
        
        if session.logger:
            session.logger.info(f"Report saved to {safe_path}")
        
        latency_ms = (time.time() - start_time) * 1000
        
        return ToolSuccess(
            data={
                "saved_to": str(safe_path),
                "size_bytes": safe_path.stat().st_size
            },
            meta=ToolMeta(latency_ms=latency_ms)
        ).to_json()
        
    except Exception as e:
        return ToolFailure(
            error=ToolError(
                code=ErrorCode.IO_ERROR.value,
                message=f"Failed to save report: {str(e)}",
                details={"exception_type": type(e).__name__}
            )
        ).to_json()
