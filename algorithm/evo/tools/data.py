"""
Data loading and inspection tools (fc_register group ``data``).

Implementation contract (README.md Phase E.1):
    - Every tool returns a **JSON string** encoding the standard envelope:
      success: {"ok": true, "data": {...}, "meta": optional}
      failure: {"ok": false, "error": {"code": "...", "message": "..."}, "details": optional}
    - Error codes include DATA_NOT_LOADED, CASE_NOT_FOUND, IO_ERROR, INVALID_ARGUMENT.
    - No hard-coded absolute user paths: defaults come from ``EvoConfig`` / session.
    - ``load_judge_data`` / ``load_trace_data`` validate schema and emit warnings
      for broken judge↔trace linkage.
    - ``get_case_detail`` must document truncation (excerpt length + full lengths).
    - ``list_bad_cases`` supports threshold, score_field, limit, offset, sort, histogram summary.

When binding to ``AnalysisSession``:
    Replace module-level stubs with callables that read/write the active session only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from lazyllm.tools import fc_register
from evo.domain.schemas import ErrorCode
from evo.tools._common import _ok, _fail
from evo.runtime.session import get_current_session


@fc_register("tool")
def load_judge_data(file_path: str | None = None) -> str:
    """
    Load judge JSON; store in session; return overview (counts, fields, warnings).

    Args:
        file_path: Optional file path override. Defaults to config.default_judge_path.

    Returns:
        JSON string per envelope spec with LoadSummary in data field.

    Error codes:
        DATA_NOT_LOADED: Session not initialized.
        IO_ERROR: File not found or JSON decode error.
        INTERNAL_ERROR: Validation or parsing error.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "No active session. Call within session_scope().")
        
        path = Path(file_path) if file_path else None
        summary = session.load_judge(path)
        
        return _ok({
            "total_cases": summary.total_cases,
            "field_histogram": summary.field_histogram,
            "sample_keys": summary.sample_keys,
            "warnings": summary.warnings
        }, start_time)
        
    except FileNotFoundError as e:
        return _fail(ErrorCode.IO_ERROR.value,
                     f"Judge file not found: {str(e)}")
        
    except json.JSONDecodeError as e:
        return _fail(ErrorCode.IO_ERROR.value,
                     f"Invalid JSON in judge file: {str(e)}")
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to load judge data: {str(e)}")


@fc_register("tool")
def load_trace_data(file_path: str | None = None) -> str:
    """
    Load trace JSON; store in session; return overview (pipeline/module stats).

    Args:
        file_path: Optional file path override. Defaults to config.default_trace_path.

    Returns:
        JSON string per envelope spec with LoadSummary in data field.

    Error codes:
        DATA_NOT_LOADED: Session not initialized.
        IO_ERROR: File not found or JSON decode error.
        INTERNAL_ERROR: Validation or parsing error.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "No active session. Call within session_scope().")
        
        path = Path(file_path) if file_path else None
        summary = session.load_trace(path)
        
        return _ok({
            "total_cases": summary.total_cases,
            "field_histogram": summary.field_histogram,
            "sample_keys": summary.sample_keys,
            "warnings": summary.warnings,
            "missing_traces": summary.missing_traces or []
        }, start_time)
        
    except FileNotFoundError as e:
        return _fail(ErrorCode.IO_ERROR.value,
                     f"Trace file not found: {str(e)}")
        
    except json.JSONDecodeError as e:
        return _fail(ErrorCode.IO_ERROR.value,
                     f"Invalid JSON in trace file: {str(e)}")
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to load trace data: {str(e)}")


@fc_register("tool")
def get_case_detail(dataset_id: str) -> str:
    """
    Merge judge + trace for ``dataset_id``; include truncation metadata.

    Args:
        dataset_id: The dataset identifier to retrieve.

    Preconditions:
        Both corpora loaded; else return DATA_NOT_LOADED with prerequisite tool names.

    Returns:
        JSON string for ``MergedCaseView``-like payload with truncation metadata.

    Truncation policy:
        - Fields longer than 500 characters are truncated with full_length included.
        - Both truncated_excerpt and full_length are provided.

    Error codes:
        DATA_NOT_LOADED: Judge or trace data not loaded.
        CASE_NOT_FOUND: Dataset ID not found.
        INVALID_ARGUMENT: Dataset ID is empty or invalid.
    """
    start_time = time.time()
    
    if not dataset_id or not isinstance(dataset_id, str):
        return _fail(ErrorCode.INVALID_ARGUMENT.value,
                     "dataset_id must be a non-empty string")
    
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "No active session. Call load_judge_data and load_trace_data first.")
        
        if session.judge_data is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Judge data not loaded. Call load_judge_data first.")
        
        if session.trace_data is None and not session._parsed_trace:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Trace data not loaded. Call load_trace_data first.")
        
        try:
            merged = session.get_merged_case(dataset_id)
        except KeyError:
            return _fail(ErrorCode.CASE_NOT_FOUND.value,
                         f"Dataset ID not found: {dataset_id}")
        except ValueError as e:
            return _fail(ErrorCode.TRACE_NOT_FOUND.value, str(e))
        
        MAX_FIELD_LENGTH = 500
        truncated_fields = {}
        
        case_dict = merged.to_dict()
        
        for field_path in [
            ("judge", "generated_answer"),
            ("judge", "gt_answer"),
            ("trace", "modules")
        ]:
            current = case_dict
            for key in field_path[:-1]:
                current = current.get(key, {})
            
            final_key = field_path[-1]
            value = current.get(final_key)
            
            if isinstance(value, str) and len(value) > MAX_FIELD_LENGTH:
                truncated_fields[f"{'.'.join(field_path)}"] = {
                    "truncated": True,
                    "excerpt": value[:MAX_FIELD_LENGTH] + "...",
                    "full_length": len(value)
                }
        
        return _ok({
            "dataset_id": merged.dataset_id,
            "query": merged.query,
            "judge": {
                "trace_id": merged.judge.trace_id,
                "answer_correctness": merged.judge.answer_correctness,
                "key": merged.judge.key,
                "hit_key": merged.judge.hit_key,
                "reason": merged.judge.reason,
                "context_recall": merged.judge.context_recall,
                "doc_recall": merged.judge.doc_recall,
                "retrieved_file": merged.judge.retrieved_file,
                "gt_file": merged.judge.gt_file,
                "retrieved_text": merged.judge.retrieved_text[:3],
                "gt_text": merged.judge.gt_text[:3],
                "generated_answer": merged.judge.generated_answer[:MAX_FIELD_LENGTH],
                "gt_answer": merged.judge.gt_answer[:MAX_FIELD_LENGTH],
                "faithfulness": merged.judge.faithfulness,
                "human_verified": merged.judge.human_verified
            },
            "trace": {
                "query": merged.trace.query,
                "pipeline": session.trace_meta.pipeline,
                "modules": {
                    k: {
                        "input": str(v.input)[:MAX_FIELD_LENGTH],
                        "output": str(v.output)[:MAX_FIELD_LENGTH] if v.output else None
                    }
                    for k, v in list(merged.trace.modules.items())[:5]
                }
            },
            "truncation_info": truncated_fields
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to get case detail: {str(e)}")


@fc_register("tool")
def list_bad_cases(
    threshold: float = 0.6,
    score_field: str | None = None,
    limit: int = 10,
    offset: int = 0,
    sort: str = "asc",
) -> str:
    """
    List paginated bad cases by metric threshold; include optional score histogram.

    Args:
        threshold: Scores strictly below are "bad". Default 0.6.
        score_field: Override config default when provided.
        limit: Maximum number of cases to return. Default 10.
        offset: Number of cases to skip. Default 0.
        sort: Sort order - ``asc`` (worst first) or ``desc`` (best among bad). Default "asc".

    Returns:
        JSON string including:
        - total_count: Total number of bad cases matching threshold.
        - cases: Array of case summaries for current page.
        - next_offset: Offset for next page, or null if no more pages.
        - histogram: Score distribution buckets.

    Error codes:
        DATA_NOT_LOADED: Judge data not loaded.
        INVALID_ARGUMENT: Invalid parameters.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None or session.judge_data is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Judge data not loaded. Call load_judge_data first.")
        
        if sort not in ("asc", "desc"):
            return _fail(ErrorCode.INVALID_ARGUMENT.value,
                         "sort must be 'asc' or 'desc'")
        
        if limit < 1 or limit > 100:
            return _fail(ErrorCode.INVALID_ARGUMENT.value,
                         "limit must be between 1 and 100")
        
        if offset < 0:
            return _fail(ErrorCode.INVALID_ARGUMENT.value,
                         "offset must be non-negative")
        
        actual_score_field = score_field or session.config.badcase_score_field
        
        all_cases = []
        for dataset_id, judge_record in session._parsed_judge.items():
            score = getattr(judge_record, actual_score_field, None)
            if score is None:
                continue
            
            if isinstance(score, (int, float)) and score < threshold:
                all_cases.append({
                    "dataset_id": dataset_id,
                    "score": score,
                    "trace_id": judge_record.trace_id,
                    "query_preview": session._parsed_trace.get(
                        judge_record.trace_id
                    ).query if judge_record.trace_id in session._parsed_trace else None
                })
        
        reverse = (sort == "desc")
        all_cases.sort(key=lambda x: x["score"], reverse=reverse)
        
        total_count = len(all_cases)
        
        histogram_buckets = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0
        }
        for case in all_cases:
            score = case["score"]
            if score < 0.2:
                histogram_buckets["0.0-0.2"] += 1
            elif score < 0.4:
                histogram_buckets["0.2-0.4"] += 1
            elif score < 0.6:
                histogram_buckets["0.4-0.6"] += 1
            elif score < 0.8:
                histogram_buckets["0.6-0.8"] += 1
            else:
                histogram_buckets["0.8-1.0"] += 1
        
        page_cases = all_cases[offset:offset + limit]
        next_offset = offset + limit if offset + limit < total_count else None
        
        return _ok({
            "total_count": total_count,
            "cases": page_cases,
            "next_offset": next_offset,
            "histogram": histogram_buckets,
            "threshold": threshold,
            "score_field": actual_score_field
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to list bad cases: {str(e)}")


@fc_register("tool")
def compare_cases(dataset_id1: str, dataset_id2: str) -> str:
    """
    Symmetric diff of metrics, pipelines, and module shapes; neutral hypothesis hints.

    Args:
        dataset_id1: First dataset ID.
        dataset_id2: Second dataset ID.

    Returns:
        JSON string with:
        - metrics_diff: Comparison of key metrics.
        - pipeline_diff: Pipeline differences.
        - module_diff: Module count and structure differences.
        - hypothesis_hints: Neutral "if-then" statements, not asserted ground truth.

    Error codes:
        DATA_NOT_LOADED: Judge or trace data not loaded.
        CASE_NOT_FOUND: One or both dataset IDs not found.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "No active session.")
        
        if session.judge_data is None or (session.trace_data is None and not session._parsed_trace):
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Both judge and trace data must be loaded first.")
        
        try:
            case1 = session.get_merged_case(dataset_id1)
            case2 = session.get_merged_case(dataset_id2)
        except KeyError as e:
            return _fail(ErrorCode.CASE_NOT_FOUND.value,
                         f"One or both cases not found: {str(e)}")
        
        metrics_to_compare = [
            "answer_correctness", "context_recall", "doc_recall", "faithfulness"
        ]
        
        metrics_diff = {}
        for metric in metrics_to_compare:
            val1 = getattr(case1.judge, metric, None)
            val2 = getattr(case2.judge, metric, None)
            if val1 is not None and val2 is not None:
                diff = val1 - val2
                metrics_diff[metric] = {
                    "case1": val1,
                    "case2": val2,
                    "diff": diff,
                    "better": "case1" if diff > 0 else ("case2" if diff < 0 else "equal")
                }
        
        ppl = session.trace_meta.pipeline if session.trace_meta.pipeline else list(case1.trace.modules.keys())
        ppl2 = session.trace_meta.pipeline if session.trace_meta.pipeline else list(case2.trace.modules.keys())
        pipeline_diff = {
            "case1_pipeline": ppl,
            "case2_pipeline": ppl2,
            "length_diff": len(ppl) - len(ppl2),
            "common_modules": list(
                set(ppl) & set(ppl2)
            ),
            "unique_to_case1": list(
                set(ppl) - set(ppl2)
            ),
            "unique_to_case2": list(
                set(ppl2) - set(ppl)
            )
        }
        
        module_diff = {
            "case1_module_count": len(case1.trace.modules),
            "case2_module_count": len(case2.trace.modules),
            "common_module_names": list(
                set(case1.trace.modules.keys()) & set(case2.trace.modules.keys())
            )
        }
        
        hypothesis_hints = []
        
        if metrics_diff.get("answer_correctness", {}).get("diff", 0) != 0:
            better_case = metrics_diff["answer_correctness"]["better"]
            if better_case == "case1":
                hint = f"If {dataset_id1} has higher correctness, examine its retrieval and generation pipeline for patterns to replicate."
            elif better_case == "case2":
                hint = f"If {dataset_id2} has higher correctness, examine its retrieval and generation pipeline for patterns to replicate."
            else:
                hint = "Both cases have similar correctness; investigate other factors."
            hypothesis_hints.append(hint)
        
        if pipeline_diff["length_diff"] != 0:
            longer = "case1" if pipeline_diff["length_diff"] > 0 else "case2"
            hint = f"If {longer} has longer pipeline, investigate whether additional modules help or hurt."
            hypothesis_hints.append(hint)
        
        return _ok({
            "dataset_id1": dataset_id1,
            "dataset_id2": dataset_id2,
            "metrics_diff": metrics_diff,
            "pipeline_diff": pipeline_diff,
            "module_diff": module_diff,
            "hypothesis_hints": hypothesis_hints
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to compare cases: {str(e)}")


@fc_register("tool")
def list_dataset_ids(
    min_score: float | None = None,
    max_score: float | None = None,
) -> str:
    """
    Enumerate dataset IDs with optional metric filters for orchestration planning.

    Args:
        min_score: Minimum score filter (inclusive).
        max_score: Maximum score filter (exclusive).

    Returns:
        JSON string list under envelope ``data`` field.

    Error codes:
        DATA_NOT_LOADED: Judge data not loaded.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None or session.judge_data is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "Judge data not loaded. Call load_judge_data first.")
        
        score_field = session.config.badcase_score_field
        
        filtered_ids = []
        for dataset_id, judge_record in session._parsed_judge.items():
            score = getattr(judge_record, score_field, None)
            if score is None:
                continue
            
            if min_score is not None and score < min_score:
                continue
            
            if max_score is not None and score >= max_score:
                continue
            
            filtered_ids.append({
                "dataset_id": dataset_id,
                "score": score
            })
        
        filtered_ids.sort(key=lambda x: x["score"])
        
        return _ok({
            "total_count": len(filtered_ids),
            "ids": filtered_ids,
            "filters": {
                "min_score": min_score,
                "max_score": max_score,
                "score_field": score_field
            }
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to list dataset IDs: {str(e)}")


@fc_register("tool")
def get_session_status() -> str:
    """
    Return loaded flags, run_id, counts, and last recoverable errors for the active session.

    Purpose:
        Reduce redundant loads and give the orchestrator model a cheap grounding call.

    Returns:
        JSON string per envelope spec with:
        - run_id: Session run identifier.
        - created_at: Session creation timestamp.
        - judge_loaded: Boolean indicating judge data is loaded.
        - trace_loaded: Boolean indicating trace data is loaded.
        - judge_case_count: Number of judge records loaded.
        - trace_case_count: Number of trace records loaded.
        - config_paths: Resolved data paths.

    Error codes:
        DATA_NOT_LOADED: No active session.
    """
    start_time = time.time()
    
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value,
                         "No active session. Initialize with session_scope().")
        
        return _ok({
            "run_id": session.run_id,
            "created_at": session.created_at.isoformat(),
            "judge_loaded": session.judge_data is not None,
            "trace_loaded": session.trace_data is not None,
            "judge_case_count": len(session._parsed_judge),
            "trace_case_count": len(session._parsed_trace),
            "config_paths": {
                "data_dir": str(session.config.data_dir),
                "output_dir": str(session.config.output_dir),
                "judge_path": str(session.config.default_judge_path),
                "trace_path": str(session.config.default_trace_path)
            }
        }, start_time)
        
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value,
                     f"Failed to get session status: {str(e)}")
