"""
Agent-first analysis pipeline.

Flow: init -> load -> step_features -> cluster -> briefing -> perspectives (parallel) -> chair -> persist.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evo.runtime.config import EvoConfig, load_config
from evo.runtime.session import AnalysisSession, create_session, session_scope


@dataclass
class PipelineResult:
    success: bool
    session: AnalysisSession
    report_path: Path | None = None
    markdown_path: Path | None = None
    artifact_paths: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class RAGAnalysisPipeline:

    def __init__(self, config: EvoConfig | None = None, logger: logging.Logger | None = None) -> None:
        self.config = config or load_config()
        self.log = logger or logging.getLogger("evo.pipeline")

    def _init(self, run_id: str | None) -> AnalysisSession:
        s = create_session(config=self.config, run_id=run_id)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        (self.config.output_dir / "reports").mkdir(exist_ok=True)
        return s

    def _load(self, s: AnalysisSession) -> None:
        jsum = s.load_judge()
        self.log.info("Judge: %d cases", jsum.total_cases)
        tsum = s.load_trace()
        self.log.info("Trace: %d records, pipeline=%s", tsum.total_cases, s.trace_meta.pipeline)

    def _compute_step_features(self, s: AnalysisSession) -> None:
        from evo.domain.step_features import build_case_step_features, aggregate_global_step_analysis
        pipeline = s.trace_meta.pipeline
        for cid in s.list_dataset_ids():
            j = s._parsed_judge.get(cid)
            if j is None:
                continue
            t = s._parsed_trace.get(j.trace_id)
            if t is None:
                continue
            s.case_step_features[cid] = build_case_step_features(j, t, pipeline)
        s.global_step_analysis = aggregate_global_step_analysis(
            s.case_step_features, s._parsed_judge, pipeline,
        )
        self.log.info("Step features: %d cases, %d steps", len(s.case_step_features), len(pipeline))

    def _cluster(self, s: AnalysisSession, badcase_limit: int, score_field: str) -> dict[str, Any]:
        from evo.tools.cluster import cluster_badcases, cluster_per_step, analyze_step_flow

        r = json.loads(cluster_badcases(score_field=score_field, limit=badcase_limit))
        if not r.get("ok"):
            raise RuntimeError(f"cluster failed: {r.get('error')}")
        data = r["data"]
        self.log.info("Clustering global: %d cases -> %d clusters", data["n_cases"], data["n_clusters"])

        r2 = json.loads(cluster_per_step(score_field=score_field, limit=badcase_limit))
        if r2.get("ok"):
            ps = r2["data"]["per_step"]
            active = [k for k, v in ps.items() if not v.get("skipped")]
            self.log.info("Clustering per-step: %d active steps", len(active))

        r3 = json.loads(analyze_step_flow())
        if r3.get("ok"):
            flow = r3["data"]
            self.log.info("Flow analysis: %d transitions, critical=%s",
                          len(flow.get("transition_analysis", [])), flow.get("critical_steps", []))

        return data

    def _collect_exemplar_ids(self, clustering: dict[str, Any]) -> list[str]:
        seen: set[str] = set()
        ids: list[str] = []
        for cs in clustering["cluster_summaries"]:
            for eid in cs["exemplar_case_ids"]:
                if eid not in seen:
                    seen.add(eid)
                    ids.append(eid)
        return ids

    def _build_briefing(self, s: AnalysisSession, clustering: dict[str, Any]) -> str:
        step_summary: dict[str, Any] = {}
        for step_key, stats in s.global_step_analysis.items():
            if not isinstance(stats, dict) or stats.get("n_cases", 0) == 0:
                continue
            highlights: dict[str, Any] = {"n_cases": stats["n_cases"]}
            for metric, vals in stats.get("stats", stats).items():
                if not isinstance(vals, dict) or "mean" not in vals:
                    continue
                entry = {"mean": vals["mean"], "std": vals.get("std", 0)}
                if vals.get("mean", 1) < 0.3 or vals.get("std", 0) > 0.4:
                    entry["anomaly"] = True
                highlights[metric] = entry
            step_summary[step_key] = highlights

        cluster_highlights = []
        for cs in clustering.get("cluster_summaries", []):
            cluster_highlights.append({
                "cluster_id": cs["cluster_id"],
                "size": cs["size"],
                "score_stats": cs.get("score_stats"),
                "top_anomalies": dict(list(cs.get("top_feature_deltas", {}).items())[:5]),
            })

        flow_summary: list[dict[str, Any]] = []
        flow_cache = s.cache.get("clustering:flow")
        if flow_cache:
            for t in flow_cache.get("transition_analysis", []):
                if t["type"] in ("divergence", "convergence"):
                    flow_summary.append({
                        "from": t["from_step"], "to": t["to_step"],
                        "type": t["type"],
                        "entropy_change": t["entropy_change"],
                        "nmi": t["nmi"],
                    })

        briefing: dict[str, Any] = {
            "flow_skeleton": s.trace_meta.flow_skeleton,
            "pipeline": s.trace_meta.pipeline,
            "step_anomaly_summary": step_summary,
            "cluster_highlights": cluster_highlights,
            "total_cases": len(s.case_step_features),
            "n_clusters": clustering.get("n_clusters", 0),
        }
        if flow_summary:
            briefing["flow_transitions"] = flow_summary
            briefing["critical_steps"] = flow_cache.get("critical_steps", [])

        return json.dumps(briefing, ensure_ascii=False, indent=2)

    def _run_perspectives(self, s: AnalysisSession, exemplar_ids: list[str],
                          clustering: dict[str, Any]) -> list[dict[str, Any]]:
        from evo.tools import register_all
        register_all()

        from evo.runtime.executor import SessionAwareExecutor
        from evo.agents.trace import TracePerspectiveAgent
        from evo.agents.judge_eval import JudgeEvalPerspectiveAgent
        from evo.agents.code import CodePerspectiveAgent
        from evo.domain.schemas import PerspectiveReport

        briefing = self._build_briefing(s, clustering)
        self.log.info("Agent briefing: %d chars", len(briefing))

        def _trace() -> dict:
            return TracePerspectiveAgent(logger=self.log).analyze(briefing, exemplar_ids).to_dict()

        def _judge() -> dict:
            return JudgeEvalPerspectiveAgent(logger=self.log).analyze(briefing, exemplar_ids).to_dict()

        def _code() -> dict:
            if not s.config.extra.get("code_map"):
                return PerspectiveReport(
                    perspective="code", dataset_ids=exemplar_ids,
                    hypotheses=[], summary="No code_map configured.",
                ).to_dict()
            return CodePerspectiveAgent(logger=self.log).analyze(briefing, exemplar_ids).to_dict()

        reports: list[dict] = []
        with SessionAwareExecutor(max_workers=3) as ex:
            futures = [ex.submit(fn) for fn in (_trace, _judge, _code)]
            for f in futures:
                try:
                    reports.append(f.result())
                except Exception as e:
                    self.log.error("Perspective agent failed: %s", e)
        self.log.info("Perspectives: %d reports", len(reports))
        return reports

    def _chair(self, s: AnalysisSession, perspectives: list[dict]) -> dict[str, Any]:
        from evo.agents.chair import ChairAgent
        result = ChairAgent(logger=self.log).synthesize(
            perspectives=perspectives,
            pipeline=s.trace_meta.pipeline,
            flow_skeleton=s.trace_meta.flow_skeleton,
            metadata={"run_id": s.run_id, "total_cases": len(s.case_step_features)},
        )
        self.log.info("Chair: %d per_step_diagnosis, %d actions, guidance=%d chars",
                      len(result.get("per_step_diagnosis", [])),
                      len(result.get("actions", [])),
                      len(result.get("guidance", "")))
        return result

    def _build_report(self, s: AnalysisSession, chair: dict[str, Any],
                      perspectives: list[dict]) -> dict[str, Any]:
        """Assemble the final report directly — no intermediate schema conversion."""
        timestamp = datetime.now()
        return {
            "report_id": f"report_{timestamp:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}",
            "metadata": {
                "created_at": timestamp.isoformat(),
                "run_id": s.run_id,
                "total_cases": len(s.case_step_features),
                "pipeline": s.trace_meta.pipeline,
            },
            "summary": chair.get("summary", ""),
            "per_step_diagnosis": chair.get("per_step_diagnosis", []),
            "actions": chair.get("actions", []),
            "guidance": chair.get("guidance", ""),
            "global_step_analysis": s.global_step_analysis,
            "flow_analysis": s.cache.get("clustering:flow"),
            "perspective_reports": [
                {"perspective": r.get("perspective"), "summary": r.get("summary", ""),
                 "n_hypotheses": len(r.get("hypotheses", [])),
                 "n_diagnosis": len(r.get("per_step_diagnosis", []))}
                for r in perspectives
            ],
        }

    def _persist(self, s: AnalysisSession, report: dict) -> dict[str, Path]:
        out_dir = s.config.output_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        rid = report["report_id"]

        json_path = out_dir / f"{rid}.json"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        s.artifact_paths["report"] = json_path
        self.log.info("Report JSON: %s", json_path)

        md_text = self._render_markdown(report)
        if md_text:
            md_path = json_path.with_suffix(".md")
            md_path.write_text(md_text, encoding="utf-8")
            s.artifact_paths["markdown"] = md_path

        return s.artifact_paths

    @staticmethod
    def _render_markdown(report: dict) -> str:
        lines = [f"# RAG 系统诊断报告", ""]
        meta = report.get("metadata", {})
        lines.append(f"- **Run**: {meta.get('run_id', 'N/A')}")
        lines.append(f"- **时间**: {meta.get('created_at', 'N/A')}")
        lines.append(f"- **案例数**: {meta.get('total_cases', 0)}")
        lines.append(f"- **Pipeline**: {' → '.join(meta.get('pipeline', []))}")
        lines.append("")

        summary = report.get("summary", "")
        if summary:
            lines.append(f"## 总结\n\n{summary}\n")

        diag = report.get("per_step_diagnosis", [])
        if diag:
            lines.append("## 步骤诊断\n")
            for i, d in enumerate(diag):
                sev = d.get("severity", "MEDIUM")
                sk = d.get("step_key", "unknown")
                lines.append(f"### {i+1}. [{sev}] {sk}\n")
                if d.get("issue"):
                    lines.append(f"**问题**: {d['issue']}\n")
                if d.get("evidence"):
                    lines.append(f"**证据**: {d['evidence']}\n")
                if d.get("root_cause"):
                    lines.append(f"**根因**: {d['root_cause']}\n")
                if d.get("suggested_fix"):
                    lines.append(f"**建议**: {d['suggested_fix']}\n")

        actions = report.get("actions", [])
        if actions:
            lines.append("## 行动项\n")
            for i, a in enumerate(actions):
                lines.append(f"{i+1}. **[{a.get('stage', '?')}]** {a.get('hypothesis', '')}")
                if a.get("suggested_changes"):
                    lines.append(f"   - 变更: {a['suggested_changes']}")
                lines.append("")

        guidance = report.get("guidance", "")
        if guidance:
            lines.append(f"## 改进指导\n\n{guidance}\n")

        return "\n".join(lines)

    def run(self, badcase_limit: int = 200, run_id: str | None = None,
            score_field: str = "answer_correctness",
            baseline_report_path: Any = None, role_perspective: str = "developer",
            **_kw: Any) -> PipelineResult:
        start = time.time()
        errors: list[str] = []
        try:
            s = self._init(run_id)
            with session_scope(s):
                self._load(s)
                self._compute_step_features(s)

                clustering = self._cluster(s, badcase_limit, score_field)
                exemplar_ids = self._collect_exemplar_ids(clustering)

                perspectives = self._run_perspectives(s, exemplar_ids, clustering)
                chair_out = self._chair(s, perspectives)
                report = self._build_report(s, chair_out, perspectives)
                arts = self._persist(s, report)
                return PipelineResult(success=True, session=s, report_path=arts.get("report"),
                                      markdown_path=arts.get("markdown"), artifact_paths=arts,
                                      elapsed_seconds=time.time() - start)
        except Exception as e:
            errors.append(str(e))
            self.log.error("Pipeline failed: %s", e, exc_info=True)
            return PipelineResult(success=False, session=create_session(config=self.config),
                                  errors=errors, elapsed_seconds=time.time() - start)
