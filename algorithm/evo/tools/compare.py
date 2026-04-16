"""Comparison & quality-check tools."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from lazyllm.tools import fc_register
from evo.domain.schemas import ErrorCode
from evo.runtime.session import get_current_session
from evo.tools._common import _ok, _fail


@fc_register("tool")
def evaluate_dataset_quality(case_ids: list[str]) -> str:
    """Inspect eval-set data quality issues."""
    start = time.time()
    if not case_ids:
        return _fail(ErrorCode.INVALID_ARGUMENT.value, "empty case_ids")
    try:
        session = get_current_session()
        if session is None or not session._parsed_judge:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No data.")
        issues: list[dict] = []
        counts: dict[str, int] = defaultdict(int)
        for did in case_ids:
            j = session._parsed_judge.get(did)
            if j is None:
                continue
            if not j.generated_answer or len(j.generated_answer.strip()) < 10:
                issues.append({"case_id": did, "issue_type": "empty_or_short_answer", "signals": {"len": len(j.generated_answer or "")}})
                counts["empty_or_short_answer"] += 1
            if j.key and len(j.key) != len(set(j.key)):
                issues.append({"case_id": did, "issue_type": "duplicate_keys", "signals": {"total": len(j.key), "unique": len(set(j.key))}})
                counts["duplicate_keys"] += 1
            if session.trace_data is not None and j.trace_id not in session._parsed_trace:
                issues.append({"case_id": did, "issue_type": "missing_trace", "signals": {"trace_id": j.trace_id}})
                counts["missing_trace"] += 1
            if not j.gt_file and not j.gt_text:
                issues.append({"case_id": did, "issue_type": "missing_gt", "signals": {}})
                counts["missing_gt"] += 1
        return _ok({"issues": issues, "summary": dict(counts), "total_checked": len(case_ids)}, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


@fc_register("tool")
def diff_metrics(before_json: str, after_json: str) -> str:
    """Compare two metric summaries and return per-metric deltas."""
    start = time.time()
    try:
        before = json.loads(before_json)
        after = json.loads(after_json)
    except json.JSONDecodeError as e:
        return _fail(ErrorCode.INVALID_ARGUMENT.value, str(e))
    bm = (before.get("data") or before).get("metrics", {})
    am = (after.get("data") or after).get("metrics", {})
    deltas: dict[str, Any] = {}
    for n in set(bm) | set(am):
        bv, av = bm.get(n, {}).get("mean"), am.get(n, {}).get("mean")
        if bv is not None and av is not None:
            d = av - bv
            deltas[n] = {"before": bv, "after": av, "delta": round(d, 4),
                         "direction": "improved" if d > 0 else ("degraded" if d < 0 else "unchanged")}
    return _ok({"deltas": deltas}, start)


@fc_register("tool")
def compare_reports(current_json: str, baseline_json: str) -> str:
    """Compare current report vs baseline for regression detection."""
    start = time.time()
    try:
        cur = json.loads(current_json)
        base = json.loads(baseline_json)
    except json.JSONDecodeError as e:
        return _fail(ErrorCode.INVALID_ARGUMENT.value, str(e))
    if "data" in cur: cur = cur["data"]
    if "data" in base: base = base["data"]

    def _acts(r: dict) -> dict[str, dict]:
        return {f"{a.get('hypothesis','')}|{a.get('trigger_metric','')}": a for a in (r.get("action_list") or {}).values()}

    ca, ba = _acts(cur), _acts(base)
    new = [{"hypothesis": ca[k].get("hypothesis", ""), "confidence": ca[k].get("evidence_confidence", 0)} for k in set(ca) - set(ba)]
    resolved = [{"hypothesis": ba[k].get("hypothesis", "")} for k in set(ba) - set(ca)]
    return _ok({"new_issues": new, "resolved": resolved, "summary": {"new": len(new), "resolved": len(resolved)}}, start)
