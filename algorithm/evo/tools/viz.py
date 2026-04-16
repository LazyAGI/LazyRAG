"""
Visualization tools (fc_register group ``visualize``).

Implementation contract (README.md Phase E.5):
    - All plots must write **only** under the current run's output directory (session-bound).
    - Return the saved file path(s) inside the JSON envelope ``data`` field.
    - Use ``evo.utils.safe_under`` to prevent directory traversal.
    - If heavy dependencies are undesirable for v1, fall back to ASCII histograms **but**
      still return a text artifact path or explicit ``kind: ascii`` metadata in ``data``.

Suggested artifacts:
    - ``plot_metric_distribution``: histogram or KDE-like bins for one metric.
    - ``plot_pipeline_length_vs_score``: scatter or aggregated buckets.
"""

from __future__ import annotations

import time

from lazyllm.tools import fc_register
from evo.domain.schemas import ErrorCode
from evo.runtime.session import get_current_session
from evo.tools._common import safe_under, _ok, _fail
from evo.tools.stats import _pearson


def _create_ascii_histogram(values: list[float], bins: int = 10, width: int = 50) -> str:
    """Create an ASCII histogram from numeric values."""
    if not values:
        return "No data available"
    
    min_val = min(values)
    max_val = max(values)
    
    if min_val == max_val:
        return f"All values: {min_val:.4f}"
    
    bin_width = (max_val - min_val) / bins
    counts = [0] * bins
    
    for val in values:
        if val >= max_val:
            idx = bins - 1
        else:
            idx = int((val - min_val) / bin_width)
        counts[idx] += 1
    
    max_count = max(counts) if counts else 1
    
    lines = []
    for i, count in enumerate(counts):
        bin_start = min_val + i * bin_width
        bin_end = bin_start + bin_width
        bar_len = int(count / max_count * width) if max_count > 0 else 0
        bar = "█" * bar_len
        
        lines.append(
            f"[{bin_start:6.2f}-{bin_end:6.2f}] "
            f"{bar} ({count})"
        )
    
    return "\n".join(lines)


@fc_register("tool")
def plot_metric_distribution(metric: str, case_ids: list[str] | None = None) -> str:
    """
    Plot the distribution of ``metric`` and persist an image or text artifact.

    Args:
        metric: Metric name to plot (e.g., "answer_correctness", "context_recall").
        case_ids: Optional list of dataset IDs. If None, uses all loaded cases.

    Returns:
        JSON envelope including:
        - artifact_path: Path to saved artifact
        - kind: "ascii" for text histograms
        - stats: Basic statistics of the metric

    Note:
        Uses ASCII histograms for v1 to avoid heavy dependencies.
        Output is a .txt file containing the histogram.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None or session.judge_data is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Judge data not loaded. Call load_judge_data first.")
        
        target_ids = case_ids if case_ids is not None else session.list_dataset_ids()
        
        values = []
        for dataset_id in target_ids:
            if dataset_id not in session._parsed_judge:
                continue
            
            judge_record = session._parsed_judge[dataset_id]
            value = getattr(judge_record, metric, None)
            
            if value is not None and isinstance(value, (int, float)):
                values.append(float(value))
        
        if not values:
            return _fail(ErrorCode.INVALID_ARGUMENT.value,
                         f"No valid values found for metric '{metric}'")
        
        stats = {
            "count": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "median": sorted(values)[len(values) // 2]
        }
        
        ascii_hist = _create_ascii_histogram(values)
        
        report_content = f"""Metric Distribution: {metric}
{'=' * 60}

Statistics:
  Count:  {stats['count']}
  Mean:   {stats['mean']:.4f}
  Median: {stats['median']:.4f}
  Min:    {stats['min']:.4f}
  Max:    {stats['max']:.4f}

Histogram:
{ascii_hist}

Generated at: {session.run_id}
"""
        
        output_dir = session.config.output_dir / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{metric}_distribution.txt"
        safe_path = safe_under(session.config.output_dir, f"plots/{filename}")
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        session.artifact_paths[f"plot_{metric}"] = safe_path
        
        return _ok({
            "artifact_path": str(safe_path),
            "kind": "ascii",
            "metric": metric,
            "stats": stats,
            "cases_included": len(target_ids),
            "valid_values": len(values),
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to plot metric distribution: {str(e)}")


@fc_register("tool")
def plot_pipeline_length_vs_score(score_field: str | None = None) -> str:
    """
    Visualize relationship between pipeline length (or module count) and a score field.

    Args:
        score_field: Metric to correlate with pipeline length. Defaults to config.badcase_score_field.

    Returns:
        JSON envelope including:
        - artifact_path: Path to saved artifact
        - kind: "ascii"
        - correlation: Correlation coefficient if computable
        - summary: Per-pipeline-length statistics

    Note:
        Uses ASCII scatter plot for v1.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None or session.judge_data is None or (session.trace_data is None and not session._parsed_trace):
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Both judge and trace data must be loaded first.")
        
        actual_score_field = score_field or session.config.badcase_score_field
        
        data_points = []
        
        for dataset_id in session.list_dataset_ids():
            try:
                merged = session.get_merged_case(dataset_id)
                
                pipeline_length = len(session.trace_meta.pipeline) if session.trace_meta.pipeline else len(merged.trace.modules)
                module_count = len(merged.trace.modules)
                score = getattr(merged.judge, actual_score_field, None)
                
                if score is not None and isinstance(score, (int, float)):
                    data_points.append({
                        "dataset_id": dataset_id,
                        "pipeline_length": pipeline_length,
                        "module_count": module_count,
                        "score": float(score)
                    })
            except (KeyError, ValueError):
                continue
        
        if not data_points:
            return _fail(ErrorCode.INVALID_ARGUMENT.value,
                         f"No valid data points for score field '{actual_score_field}'")
        
        by_pipeline_length: dict[int, list[float]] = {}
        for dp in data_points:
            pl = dp["pipeline_length"]
            if pl not in by_pipeline_length:
                by_pipeline_length[pl] = []
            by_pipeline_length[pl].append(dp["score"])
        
        summary_stats = {}
        for pl, scores in sorted(by_pipeline_length.items()):
            summary_stats[pl] = {
                "count": len(scores),
                "mean": sum(scores) / len(scores),
                "min": min(scores),
                "max": max(scores)
            }
        
        correlation = None
        if len(data_points) > 1:
            x_vals = [dp["pipeline_length"] for dp in data_points]
            y_vals = [dp["score"] for dp in data_points]
            correlation = _pearson(x_vals, y_vals)
        
        lines = []
        lines.append(f"Pipeline Length vs {actual_score_field}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Correlation: {correlation:.4f}" if correlation is not None else "Correlation: N/A")
        lines.append("")
        lines.append("Statistics by Pipeline Length:")
        lines.append("-" * 60)
        lines.append(f"{'Length':<8} {'Count':<8} {'Mean':<10} {'Min':<10} {'Max':<10}")
        lines.append("-" * 60)
        
        for pl, stats in sorted(summary_stats.items()):
            lines.append(
                f"{pl:<8} {stats['count']:<8} "
                f"{stats['mean']:<10.4f} {stats['min']:<10.4f} {stats['max']:<10.4f}"
            )
        
        lines.append("")
        lines.append("ASCII Scatter Plot (Pipeline Length vs Score):")
        lines.append("-" * 60)
        
        for dp in sorted(data_points, key=lambda x: x["pipeline_length"]):
            pl = dp["pipeline_length"]
            score = dp["score"]
            bar_len = int(score * 20)
            bar = "●" * bar_len
            lines.append(f"Length {pl}: {bar} {score:.2f}")
        
        lines.append("")
        lines.append(f"Generated at: {session.run_id}")
        
        report_content = "\n".join(lines)
        
        output_dir = session.config.output_dir / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"pipeline_vs_{actual_score_field}.txt"
        safe_path = safe_under(session.config.output_dir, f"plots/{filename}")
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        session.artifact_paths[f"plot_pipeline_vs_{actual_score_field}"] = safe_path
        
        return _ok({
            "artifact_path": str(safe_path),
            "kind": "ascii",
            "correlation": round(correlation, 4) if correlation is not None else None,
            "summary_by_length": {
                str(k): v for k, v in summary_stats.items()
            },
            "total_cases": len(data_points),
            "score_field": actual_score_field,
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to plot pipeline vs score: {str(e)}")
