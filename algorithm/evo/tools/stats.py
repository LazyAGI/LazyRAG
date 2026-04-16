"""
Corpus-level statistics tools (fc_register group ``stats``).

Implementation contract (README.md Phase E.4):
    - ``summarize_metrics``: mean/median/p10/p90 for key metrics; missing-field counts;
      optional filter by ``case_ids`` (all loaded cases when omitted).
    - ``correlate_metrics``: lightweight correlation / co-movement summaries with small-sample warnings.

Outputs must use the standard JSON envelope as a string.
"""

from __future__ import annotations

import math
import time
from typing import Any

from lazyllm.tools import fc_register
from evo.domain.schemas import ErrorCode
from evo.tools._common import _ok, _fail
from evo.runtime.session import get_current_session


def _percentile(sorted_values: list[float], p: float) -> float:
    """Calculate percentile from sorted values."""
    if not sorted_values:
        return 0.0
    
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    
    k = (n - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    
    if f == c:
        return sorted_values[int(k)]
    
    return sorted_values[int(f)] * (c - k) + sorted_values[int(c)] * (k - f)


@fc_register("tool")
def summarize_metrics(case_ids: list[str] | None = None) -> str:
    """
    Summarize metric distributions across the corpus or a subset.

    Args:
        case_ids: When None, include every loaded dataset id (excluding structural keys).

    Returns:
        JSON string with:
        - metrics: Dict of metric_name -> {mean, median, min, max, p10, p90, count, missing_count}
        - total_cases: Number of cases included
        - filtered: Boolean indicating if case_ids filter was applied

    Error codes:
        DATA_NOT_LOADED: Judge data not loaded.
        INVALID_ARGUMENT: Empty case_ids list provided.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None or session.judge_data is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "Judge data not loaded. Call load_judge_data first.")
        
        if case_ids is not None:
            if not isinstance(case_ids, list):
                return _fail(ErrorCode.INVALID_ARGUMENT.value, "case_ids must be a list or None")
            
            if len(case_ids) == 0:
                return _fail(ErrorCode.INVALID_ARGUMENT.value, "case_ids list cannot be empty (use None for all cases)")
        
        target_ids = case_ids if case_ids is not None else session.list_dataset_ids()
        
        metrics_to_analyze = [
            "answer_correctness",
            "context_recall",
            "doc_recall",
            "faithfulness"
        ]
        
        metrics_values: dict[str, list[float]] = {m: [] for m in metrics_to_analyze}
        missing_counts: dict[str, int] = {m: 0 for m in metrics_to_analyze}
        
        for dataset_id in target_ids:
            if dataset_id not in session._parsed_judge:
                continue
            
            judge_record = session._parsed_judge[dataset_id]
            
            for metric in metrics_to_analyze:
                value = getattr(judge_record, metric, None)
                if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
                    missing_counts[metric] += 1
                else:
                    try:
                        metrics_values[metric].append(float(value))
                    except (TypeError, ValueError):
                        missing_counts[metric] += 1
        
        metrics_summary = {}
        for metric in metrics_to_analyze:
            values = sorted(metrics_values[metric])
            
            if not values:
                metrics_summary[metric] = {
                    "mean": None,
                    "median": None,
                    "min": None,
                    "max": None,
                    "p10": None,
                    "p90": None,
                    "count": 0,
                    "missing_count": missing_counts[metric]
                }
            else:
                mean_val = sum(values) / len(values)
                median_val = _percentile(values, 50)
                p10_val = _percentile(values, 10)
                p90_val = _percentile(values, 90)
                
                metrics_summary[metric] = {
                    "mean": round(mean_val, 4),
                    "median": round(median_val, 4),
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "p10": round(p10_val, 4),
                    "p90": round(p90_val, 4),
                    "count": len(values),
                    "missing_count": missing_counts[metric]
                }
        
        key_hit_stats = {"total_keys": 0, "total_hit_keys": 0, "avg_hit_rate": 0.0}
        key_counts = []
        
        for dataset_id in target_ids:
            if dataset_id not in session._parsed_judge:
                continue
            
            judge_record = session._parsed_judge[dataset_id]
            total = len(judge_record.key)
            hit = len(judge_record.hit_key)
            
            key_hit_stats["total_keys"] += total
            key_hit_stats["total_hit_keys"] += hit
            
            if total > 0:
                key_counts.append(hit / total)
        
        if key_counts:
            key_hit_stats["avg_hit_rate"] = round(sum(key_counts) / len(key_counts), 4)
        
        return _ok({
                "metrics": metrics_summary,
                "key_hit_stats": key_hit_stats,
                "total_cases": len(target_ids),
                "filtered": case_ids is not None
            }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, f"Failed to summarize metrics: {str(e)}")


# ---------------------------------------------------------------------------
# Correlation primitives (pure Python, no scipy/numpy required)
# ---------------------------------------------------------------------------

def _pearson(x: list[float], y: list[float]) -> float | None:
    """Pearson product-moment correlation coefficient."""
    n = len(x)
    if n < 2:
        return None
    sx = sum(x)
    sy = sum(y)
    sxy = sum(a * b for a, b in zip(x, y))
    sx2 = sum(a * a for a in x)
    sy2 = sum(b * b for b in y)
    num = n * sxy - sx * sy
    dx = math.sqrt(max(n * sx2 - sx * sx, 0))
    dy = math.sqrt(max(n * sy2 - sy * sy, 0))
    if dx == 0 or dy == 0:
        return None
    return max(-1.0, min(1.0, num / (dx * dy)))


def _rank(values: list[float]) -> list[float]:
    """Assign average ranks (handles ties)."""
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j - 1) / 2.0 + 1
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def _spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation (monotonic relationships, outlier-robust)."""
    if len(x) < 2:
        return None
    return _pearson(_rank(x), _rank(y))


def _kendall(x: list[float], y: list[float]) -> float | None:
    """Kendall's Tau-b (stable for small samples, ordinal data)."""
    n = len(x)
    if n < 2:
        return None
    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[i] - x[j]
            dy = y[i] - y[j]
            if dx == 0 and dy == 0:
                ties_x += 1
                ties_y += 1
            elif dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif (dx > 0 and dy > 0) or (dx < 0 and dy < 0):
                concordant += 1
            else:
                discordant += 1
    n_pairs = n * (n - 1) / 2
    denom = math.sqrt((n_pairs - ties_x) * (n_pairs - ties_y))
    if denom == 0:
        return None
    return (concordant - discordant) / denom


def _partial_correlation(
    x: list[float], y: list[float], controls: list[list[float]]
) -> float | None:
    """
    Partial correlation via residual method (no sklearn needed).

    Regresses x and y on the control variables using OLS, then computes
    Pearson correlation on the residuals.
    """
    n = len(x)
    if n < 3 or not controls:
        return _pearson(x, y)

    def _residuals(target: list[float], predictors: list[list[float]]) -> list[float]:
        k = len(predictors)
        xt = [[1.0] + [predictors[c][i] for c in range(k)] for i in range(n)]

        xTx = [[sum(xt[r][a] * xt[r][b] for r in range(n)) for b in range(k + 1)] for a in range(k + 1)]
        xTy = [sum(xt[r][a] * target[r] for r in range(n)) for a in range(k + 1)]

        # Gauss elimination
        m = k + 1
        aug = [row[:] + [xTy[i]] for i, row in enumerate(xTx)]
        for col in range(m):
            pivot = max(range(col, m), key=lambda r: abs(aug[r][col]))
            aug[col], aug[pivot] = aug[pivot], aug[col]
            if abs(aug[col][col]) < 1e-12:
                return target  # singular → return original
            for row in range(col + 1, m):
                f = aug[row][col] / aug[col][col]
                for j in range(col, m + 1):
                    aug[row][j] -= f * aug[col][j]
        beta = [0.0] * m
        for i in range(m - 1, -1, -1):
            beta[i] = aug[i][m]
            for j in range(i + 1, m):
                beta[i] -= aug[i][j] * beta[j]
            beta[i] /= aug[i][i]

        return [target[r] - sum(xt[r][a] * beta[a] for a in range(m)) for r in range(n)]

    rx = _residuals(x, controls)
    ry = _residuals(y, controls)
    return _pearson(rx, ry)


def _collect_metric_vectors(
    session: Any, target_ids: list[str], metrics: list[str]
) -> dict[str, list[float]]:
    """Collect aligned metric vectors (cases with any missing value are excluded)."""
    data: dict[str, list[float]] = {m: [] for m in metrics}
    for did in target_ids:
        j = session._parsed_judge.get(did)
        if j is None:
            continue
        vals: dict[str, float] = {}
        skip = False
        for m in metrics:
            v = getattr(j, m, None)
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                skip = True
                break
            try:
                vals[m] = float(v)
            except (TypeError, ValueError):
                skip = True
                break
        if skip:
            continue
        for m in metrics:
            data[m].append(vals[m])
    return data


def _interpret_strength(r: float | None) -> str:
    if r is None:
        return "N/A"
    a = abs(r)
    if a >= 0.8:
        return "very_strong"
    if a >= 0.6:
        return "strong"
    if a >= 0.4:
        return "moderate"
    if a >= 0.2:
        return "weak"
    return "negligible"


# ---------------------------------------------------------------------------
# Backward-compatible simple correlate_metrics (Pearson only)
# ---------------------------------------------------------------------------

@fc_register("tool")
def correlate_metrics(case_ids: list[str] | None = None) -> str:
    """
    Compute Pearson correlations between key metrics (backward-compatible).

    For multi-method analysis, use ``correlate_metrics_enhanced`` instead.

    Args:
        case_ids: When None, include every loaded dataset id.

    Returns:
        JSON envelope with Pearson correlations, sample_size, warnings.
    """
    return correlate_metrics_enhanced(case_ids=case_ids, methods=["pearson"])


# ---------------------------------------------------------------------------
# Enhanced multi-method correlation tool
# ---------------------------------------------------------------------------

@fc_register("tool")
def correlate_metrics_enhanced(
    case_ids: list[str] | None = None,
    methods: list[str] | None = None,
    control_variables: list[str] | None = None,
) -> str:
    """
    Multi-method correlation analysis with consensus detection.

    Supported methods:
        - pearson: linear correlation (classic)
        - spearman: rank correlation (monotonic, outlier-robust)
        - kendall: Kendall's Tau-b (small-sample stable, ordinal)
        - partial: partial correlation controlling for confounders

    Args:
        case_ids: Target case list (None = all loaded).
        methods: Which methods to run (default: all except partial).
        control_variables: Metric names to control for in partial correlation
                           (e.g. ["doc_recall"] to remove its confounding effect).

    Returns:
        JSON envelope with per-method correlation matrices, consensus
        correlations, and warnings.
    """
    start_time = time.time()
    valid_methods = {"pearson", "spearman", "kendall", "partial"}

    if methods is None:
        methods = ["pearson", "spearman", "kendall"]
    unknown = set(methods) - valid_methods
    if unknown:
        return _fail(ErrorCode.INVALID_ARGUMENT.value, f"Unknown methods: {unknown}. Supported: {valid_methods}")

    try:
        session = get_current_session()
        if session is None or session.judge_data is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "Judge data not loaded. Call load_judge_data first.")

        target_ids = case_ids if case_ids is not None else session.list_dataset_ids()
        all_metrics = ["answer_correctness", "context_recall", "doc_recall", "faithfulness"]
        data = _collect_metric_vectors(session, target_ids, all_metrics)

        n = len(data[all_metrics[0]]) if all_metrics else 0
        warnings: list[str] = []
        if n < 3:
            warnings.append(f"Only {n} complete cases; correlations are unreliable")
        elif n < 10:
            warnings.append(f"Small sample ({n} cases); interpret with caution")

        results: dict[str, Any] = {}
        method_funcs: dict[str, Any] = {
            "pearson": _pearson,
            "spearman": _spearman,
            "kendall": _kendall,
        }

        for method in methods:
            if method == "partial":
                if not control_variables:
                    results["partial"] = {
                        "note": "Specify control_variables to compute partial correlations"
                    }
                    continue
                missing_ctrl = [c for c in control_variables if c not in data]
                if missing_ctrl:
                    results["partial"] = {"error": f"Control variables not found: {missing_ctrl}"}
                    continue
                ctrl_vecs = [data[c] for c in control_variables]
                analyze_metrics = [m for m in all_metrics if m not in control_variables]
                partial_res: dict[str, Any] = {}
                for i, m1 in enumerate(analyze_metrics):
                    for m2 in analyze_metrics[i + 1:]:
                        r = _partial_correlation(data[m1], data[m2], ctrl_vecs)
                        key = f"{m1}_vs_{m2}_ctrl_{'_'.join(control_variables)}"
                        partial_res[key] = {
                            "coefficient": round(r, 4) if r is not None else None,
                            "strength": _interpret_strength(r),
                            "sample_size": n,
                            "controlled_for": control_variables,
                        }
                results["partial"] = partial_res
                continue

            fn = method_funcs[method]
            matrix: dict[str, Any] = {}
            for i, m1 in enumerate(all_metrics):
                for m2 in all_metrics[i + 1:]:
                    r = fn(data[m1], data[m2])
                    key = f"{m1}_vs_{m2}"
                    matrix[key] = {
                        "coefficient": round(r, 4) if r is not None else None,
                        "strength": _interpret_strength(r),
                        "sample_size": n,
                    }
            results[method] = matrix

        consensus = _find_consensus(results, all_metrics)

        return _ok({
                "methods_used": methods,
                "results": results,
                "consensus": consensus,
                "sample_size": n,
                "warnings": warnings,
            }, start_time)

    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, f"correlate_metrics_enhanced failed: {e}")


def _find_consensus(results: dict[str, Any], metrics: list[str]) -> dict[str, Any]:
    """
    Identify metric pairs where multiple methods agree on the direction and strength.

    A pair is "consensus significant" when at least 2 methods report |r| >= 0.4
    in the same direction.
    """
    pair_scores: dict[str, list[float]] = {}
    for method, matrix in results.items():
        if not isinstance(matrix, dict):
            continue
        for key, val in matrix.items():
            if not isinstance(val, dict):
                continue
            coef = val.get("coefficient")
            if coef is not None:
                pair_scores.setdefault(key, []).append(coef)

    consensus: dict[str, Any] = {}
    for pair, scores in pair_scores.items():
        significant = [s for s in scores if abs(s) >= 0.4]
        if len(significant) < 2:
            continue
        directions = [1 if s > 0 else -1 for s in significant]
        if len(set(directions)) != 1:
            continue
        consensus[pair] = {
            "methods_agreeing": len(significant),
            "mean_coefficient": round(sum(significant) / len(significant), 4),
            "direction": "positive" if directions[0] > 0 else "negative",
            "strength": _interpret_strength(sum(significant) / len(significant)),
            "confidence": "high" if len(significant) >= 3 else "medium",
        }
    return consensus
