"""Analysis session: per-run state bound via ContextVar."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evo.runtime.config import EvoConfig
from evo.domain.models import (
    JudgeRecord, TraceRecord, TraceMeta, MergedCaseView, LoadSummary,
    parse_judge_record, parse_trace_file, parse_eval_report,
)

def _infer_trace_meta(traces: dict[str, TraceRecord]) -> TraceMeta:
    """Derive TraceMeta from eval-format traces (no execution_tree)."""
    for t in traces.values():
        if t.modules:
            pipeline = list(t.modules.keys())
            return TraceMeta(pipeline=pipeline, flow_skeleton=[
                {"type": "flow", "name": "Pipeline", "children_count": len(pipeline)},
                *[{"type": "module", "key": k, "name": k} for k in pipeline],
            ])
    return TraceMeta()

_current_session: ContextVar["AnalysisSession | None"] = ContextVar("evo_session", default=None)


def get_current_session() -> AnalysisSession | None:
    return _current_session.get()


class session_scope:
    """Context manager that binds a session to the current ContextVar."""

    def __init__(self, session: AnalysisSession) -> None:
        self._session = session
        self._token: Any = None

    def __enter__(self) -> AnalysisSession:
        self._token = _current_session.set(self._session)
        return self._session

    def __exit__(self, *exc: Any) -> None:
        _current_session.reset(self._token)


def create_session(config: EvoConfig | None = None, run_id: str | None = None) -> AnalysisSession:
    if config is None:
        from evo.runtime.config import load_config
        config = load_config()
    if run_id is None:
        run_id = f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
    return AnalysisSession(run_id=run_id, created_at=datetime.now(), config=config)


@dataclass
class AnalysisSession:
    run_id: str
    created_at: datetime
    config: EvoConfig
    judge_data: dict[str, Any] | None = None
    trace_data: dict[str, Any] | None = None
    feature_cache: dict[tuple[Any, ...], Any] = field(default_factory=dict)
    artifact_paths: dict[str, Path] = field(default_factory=dict)
    logger: logging.Logger | None = None
    _parsed_judge: dict[str, JudgeRecord] = field(default_factory=dict)
    _parsed_trace: dict[str, TraceRecord] = field(default_factory=dict)
    trace_meta: TraceMeta = field(default_factory=TraceMeta)
    case_step_features: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    global_step_analysis: dict[str, Any] = field(default_factory=dict)
    _warnings: list[str] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.logger is None:
            self.logger = logging.getLogger(f"evo.session.{self.run_id}")

    def list_dataset_ids(self) -> list[str]:
        return list(self._parsed_judge.keys())

    def get_merged_case(self, dataset_id: str) -> MergedCaseView:
        if dataset_id not in self._parsed_judge:
            raise KeyError(f"Dataset ID not found: {dataset_id}")
        j = self._parsed_judge[dataset_id]
        t = self._parsed_trace.get(j.trace_id)
        if t is None:
            raise ValueError(f"Trace {j.trace_id} not found for {dataset_id}")
        return MergedCaseView(dataset_id=dataset_id, query=t.query, judge=j, trace=t)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_judge(self, path: Path | None = None) -> LoadSummary:
        start = time.time()
        path = Path(path or self.config.default_judge_path)
        if not path.exists():
            raise FileNotFoundError(f"Judge file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.judge_data = raw
        self._warnings = []
        if "case_details" in raw and isinstance(raw.get("case_details"), list):
            return self._load_eval_format(raw, start)
        return self._load_legacy_format(raw, start)

    def _load_eval_format(self, raw: dict, start: float) -> LoadSummary:
        jm, tm, meta, warns = parse_eval_report(raw)
        self._parsed_judge, self._parsed_trace = jm, tm
        self.trace_meta = _infer_trace_meta(tm)
        self._warnings.extend(warns)
        self.config.extra["eval_report_meta"] = meta
        hist: dict[str, int] = {}
        for j in jm.values():
            for fn in vars(j):
                if not fn.startswith("_"):
                    hist[fn] = hist.get(fn, 0) + 1
        if self.logger:
            self.logger.info("Loaded %d cases (eval format) in %.3fs", len(jm), time.time() - start)
        return LoadSummary(total_cases=len(jm), field_histogram=hist, sample_keys=list(jm)[:5], warnings=self._warnings[:])

    def _load_legacy_format(self, raw: dict, start: float) -> LoadSummary:
        keys = [k for k in raw if k != "count"]
        hist: dict[str, int] = {}
        self._parsed_judge = {}
        for did in keys:
            try:
                rec, w = parse_judge_record(raw[did])
                self._parsed_judge[did] = rec
                self._warnings.extend(f"[{did}] {x}" for x in w)
                for fn in raw[did]:
                    hist[fn] = hist.get(fn, 0) + 1
            except ValueError as e:
                self._warnings.append(f"[{did}] {e}")
        if self.logger:
            self.logger.info("Loaded %d judge records in %.3fs", len(self._parsed_judge), time.time() - start)
        return LoadSummary(total_cases=len(self._parsed_judge), field_histogram=hist, sample_keys=keys[:5], warnings=self._warnings[:])

    def load_trace(self, path: Path | None = None) -> LoadSummary:
        path = Path(path or self.config.default_trace_path)
        if not path.exists():
            if self._parsed_trace:
                return LoadSummary(total_cases=len(self._parsed_trace), field_histogram={},
                                   sample_keys=list(self._parsed_trace)[:5], warnings=[])
            raise FileNotFoundError(f"Trace file not found: {path}")
        start = time.time()
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.trace_data = raw
        meta, traces, warns = parse_trace_file(raw)
        if meta.pipeline:
            self.trace_meta = meta
        for tid, tr in traces.items():
            self._parsed_trace[tid] = tr
        self._warnings.extend(warns)
        missing = [f"{did}->{self._parsed_judge[did].trace_id}" for did in self._parsed_judge if self._parsed_judge[did].trace_id not in self._parsed_trace] if self._parsed_judge else []
        if self.logger:
            self.logger.info("Loaded %d traces in %.3fs (meta pipeline=%s)", len(self._parsed_trace), time.time() - start, self.trace_meta.pipeline)
        keys = list(self._parsed_trace.keys())
        return LoadSummary(total_cases=len(self._parsed_trace), field_histogram={}, sample_keys=keys[:5], warnings=self._warnings[:], missing_traces=missing or None)
