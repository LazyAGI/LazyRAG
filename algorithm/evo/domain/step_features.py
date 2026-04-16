"""Per-step feature extraction driven by IO data shape, not step names."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
from scipy.special import softmax
from scipy.stats import entropy as scipy_entropy, kendalltau
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import jaccard_score

from evo.domain.models import JudgeRecord, TraceRecord, ModuleOutput


# ---------------------------------------------------------------------------
# IO introspection helpers
# ---------------------------------------------------------------------------

def _extract_ids(data: Any) -> list[str]:
    """Extract ordered ID list from list-of-dicts output/input."""
    if not isinstance(data, list):
        return []
    return [item.get("id", item.get("file_name", item.get("chunk_id", "")))
            for item in data if isinstance(item, dict) and
            (item.get("id") or item.get("file_name") or item.get("chunk_id"))]


def _get_args(inp: Any) -> list[Any]:
    if isinstance(inp, dict):
        return inp.get("args", [])
    if isinstance(inp, list):
        return inp
    return [inp] if inp else []


def _extract_text(data: Any) -> str:
    """Extract the main text content from various shapes."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("context_str", "text", "content", "query"):
            if isinstance(data.get(key), str) and len(data[key]) > 10:
                return data[key]
        return " ".join(str(v) for v in data.values() if isinstance(v, str))
    if isinstance(data, list) and data and isinstance(data[0], (str, dict)):
        return _extract_text(data[0])
    return str(data) if data else ""


def _text_len(val: Any) -> int:
    if isinstance(val, str):
        return len(val)
    if isinstance(val, dict):
        return sum(_text_len(v) for v in val.values())
    if isinstance(val, list):
        return sum(_text_len(v) for v in val)
    return 0


def _text_jaccard(text_a: str, text_b: str) -> float:
    """Jaccard similarity between word sets of two texts via sklearn."""
    if not text_a.strip() or not text_b.strip():
        return 0.0
    vec = CountVectorizer(binary=True, lowercase=True)
    try:
        X = vec.fit_transform([text_a, text_b])
    except ValueError:
        return 0.0
    return float(jaccard_score(
        X[0].toarray().ravel(), X[1].toarray().ravel(),
        average="binary", zero_division=0.0,
    ))


def _is_text(data: Any) -> bool:
    if isinstance(data, str) and len(data) > 10:
        return True
    if isinstance(data, dict):
        return any(isinstance(v, str) and len(v) > 20 for v in data.values())
    return False


# ---------------------------------------------------------------------------
# Feature computation by IO shape
# ---------------------------------------------------------------------------

def _ids_output_features(out_ids: list[str], gt_ids: set[str],
                         scores: np.ndarray) -> dict[str, float]:
    """Features when output contains document IDs."""
    f: dict[str, float] = {}
    out_arr = np.array(out_ids)
    gt_arr = np.array(list(gt_ids)) if gt_ids else np.empty(0, dtype=str)
    gt_mask = np.isin(out_arr, gt_arr)

    f["retrieval_count"] = float(out_arr.size)

    if gt_ids:
        f["recall_at_k"] = float(gt_mask.sum() / len(gt_ids))
        f["precision_at_k"] = float(np.mean(gt_mask)) if out_arr.size else 0.0

        if scores.size == out_arr.size:
            rank_order = np.argsort(-scores)
            ranked_gt = np.isin(out_arr[rank_order], gt_arr)
        else:
            ranked_gt = gt_mask

        hit_pos = np.flatnonzero(ranked_gt)
        f["mrr"] = float(1.0 / (hit_pos[0] + 1)) if hit_pos.size > 0 else 0.0
        f["gt_in_top1"] = float(ranked_gt[0]) if ranked_gt.size > 0 else 0.0

    if scores.size:
        f["score_mean"] = float(np.mean(scores))
        f["score_max"] = float(np.max(scores))
        f["score_min"] = float(np.min(scores))
        if scores.size >= 2:
            f["score_std"] = float(np.std(scores))
            sorted_s = np.sort(scores)
            f["top1_margin"] = float(sorted_s[-1] - sorted_s[-2])
            f["score_gap"] = float(sorted_s[-1] - sorted_s[0])
            if sorted_s[-1] != 0:
                f["score_confidence"] = float(
                    (sorted_s[-1] - sorted_s[-2]) / abs(sorted_s[-1])
                )
            f["score_entropy"] = float(scipy_entropy(softmax(scores)))

    return f


def _filtering_features(in_ids: list[str], out_ids: list[str],
                         gt_ids: set[str]) -> dict[str, float]:
    """Features when both input and output contain IDs (filtering/reranking)."""
    f: dict[str, float] = {}
    in_arr = np.array(in_ids)
    out_arr = np.array(out_ids)
    gt_arr = np.array(list(gt_ids)) if gt_ids else np.empty(0, dtype=str)

    f["input_count"] = float(in_arr.size)
    f["output_count"] = float(out_arr.size)
    f["selectivity"] = float(out_arr.size / in_arr.size) if in_arr.size else 0.0

    if gt_ids:
        in_gt = np.isin(in_arr, gt_arr)
        out_gt = np.isin(out_arr, gt_arr)
        survived = np.isin(in_arr, out_arr)

        in_hits = int(in_gt.sum())
        out_hits = int(out_gt.sum())
        f["input_recall"] = float(in_hits / len(gt_ids))
        f["output_recall"] = float(out_hits / len(gt_ids))
        f["recall_delta"] = f["output_recall"] - f["input_recall"]

        gt_survived = int((in_gt & survived).sum())
        f["gt_survival_rate"] = float(gt_survived / in_hits) if in_hits > 0 else 1.0
        f["gt_drop_count"] = float(in_hits - gt_survived)
        f["non_gt_drop_count"] = float((~in_gt & ~survived).sum())

        gt_in_input = np.flatnonzero(in_gt)
        if gt_in_input.size:
            first_gt = in_arr[gt_in_input[0]]
            out_pos = np.flatnonzero(out_arr == first_gt)
            if out_pos.size:
                f["gt_rank_shift"] = float(gt_in_input[0] - out_pos[0])

    if in_arr.size >= 2 and out_arr.size >= 2:
        in_rank = {doc: r for r, doc in enumerate(in_ids)}
        mapped = [in_rank[d] for d in out_ids if d in in_rank]
        if len(mapped) >= 2:
            tau, _ = kendalltau(np.arange(len(mapped)), mapped)
            if np.isfinite(tau):
                f["rank_correlation"] = float(tau)

    return f


def _text_output_features(mod: ModuleOutput, judge: JudgeRecord) -> dict[str, float]:
    """Features when output is text (generation/formatting)."""
    f: dict[str, float] = {}
    out_text = _extract_text(mod.output)
    in_text = _extract_text(_get_args(mod.input))

    f["output_text_len"] = float(len(out_text))
    f["input_context_len"] = float(len(in_text))
    f["answer_context_ratio"] = len(out_text) / max(len(in_text), 1)

    if judge.gt_answer:
        gt_len = len(judge.gt_answer)
        f["answer_length_ratio"] = float(len(out_text) / gt_len) if gt_len else 0.0

    if in_text:
        f["context_utilization"] = _text_jaccard(out_text, in_text)
    if judge.gt_answer:
        f["answer_gt_overlap"] = _text_jaccard(out_text, judge.gt_answer)

    if out_text:
        char_freq = np.array(list(Counter(out_text).values()), dtype=np.float64)
        f["answer_entropy"] = float(scipy_entropy(char_freq / char_freq.sum()))

    if len(out_text) >= 3:
        trigrams = [out_text[i:i + 3] for i in range(len(out_text) - 2)]
        tri_counts = Counter(trigrams)
        repeated = sum(c - 1 for c in tri_counts.values() if c > 1)
        f["repetition_rate"] = float(repeated / len(trigrams))

    return f


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def features_for_step(
    mod: ModuleOutput,
    gt_ids: set[str],
    judge: JudgeRecord,
) -> dict[str, float]:
    """Compute features based on IO data shape, not step name."""
    f: dict[str, float] = {}
    args = _get_args(mod.input)
    scores = np.array(mod.scores, dtype=np.float64) if mod.scores else np.empty(0)

    in_ids = _extract_ids(args)
    out_ids = _extract_ids(mod.output)
    out_is_text = _is_text(mod.output)

    f["input_text_len"] = float(_text_len(mod.input))
    f["output_text_len"] = float(_text_len(mod.output))

    if out_ids:
        f.update(_ids_output_features(out_ids, gt_ids, scores))
        if in_ids:
            f.update(_filtering_features(in_ids, out_ids, gt_ids))

    if out_is_text:
        f.update(_text_output_features(mod, judge))

    f["global_correctness"] = judge.answer_correctness

    return {k: round(v, 6) for k, v in f.items()}


def build_case_step_features(
    judge: JudgeRecord,
    trace: TraceRecord,
    pipeline: list[str],
) -> dict[str, dict[str, float]]:
    """For one case, compute features for every step in pipeline order."""
    gt_ids = set(judge.gt_file) | set(judge.retrieved_file)
    result: dict[str, dict[str, float]] = {}
    for key in pipeline:
        mod = trace.modules.get(key)
        if mod is None:
            continue
        result[key] = features_for_step(mod, gt_ids, judge)
    return result


def flatten_case_features(step_feats: dict[str, dict[str, float]]) -> dict[str, float]:
    """Flatten per-step features into ``step_key:metric`` for clustering."""
    flat: dict[str, float] = {}
    for step_key, metrics in step_feats.items():
        for metric, val in metrics.items():
            flat[f"{step_key}:{metric}"] = val
    return flat


def build_step_matrix(
    all_case_feats: dict[str, dict[str, dict[str, float]]],
    step_key: str,
    target_ids: set[str] | None = None,
) -> tuple[list[str], list[str], np.ndarray]:
    """Build a case x feature matrix for a single step. Drops zero-variance columns."""
    ids, rows = [], []
    for cid, sf in all_case_feats.items():
        if target_ids and cid not in target_ids:
            continue
        step_feats = sf.get(step_key, {})
        if step_feats:
            ids.append(cid)
            rows.append(step_feats)
    if not rows:
        return [], [], np.empty((0, 0))
    all_keys = sorted({k for r in rows for k in r})
    mat = np.array([[r.get(k, 0.0) for k in all_keys] for r in rows], dtype=np.float64)
    np.nan_to_num(mat, copy=False)
    std = mat.std(axis=0)
    keep = std > 0
    if keep.sum() < 2:
        return [], [], np.empty((0, 0))
    return ids, [k for k, m in zip(all_keys, keep) if m], mat[:, keep]


def aggregate_global_step_analysis(
    all_case_feats: dict[str, dict[str, dict[str, float]]],
    all_judge: dict[str, JudgeRecord],
    pipeline: list[str],
) -> dict[str, Any]:
    """Aggregate per-step features across all cases for each pipeline step."""
    result: dict[str, Any] = {}
    case_ids = list(all_case_feats.keys())
    if not case_ids:
        return result

    correctness = np.array([all_judge[cid].answer_correctness for cid in case_ids if cid in all_judge], dtype=np.float64)

    for step_key in pipeline:
        step_vectors: dict[str, list[float]] = {}
        for cid in case_ids:
            sf = all_case_feats[cid].get(step_key, {})
            for metric, val in sf.items():
                step_vectors.setdefault(metric, []).append(val)

        if not step_vectors:
            result[step_key] = {"n_cases": 0}
            continue

        stats: dict[str, Any] = {}
        for metric, vals in step_vectors.items():
            arr = np.array(vals, dtype=np.float64)
            stats[metric] = {
                "mean": round(float(arr.mean()), 4),
                "std": round(float(arr.std()), 4),
                "min": round(float(arr.min()), 4),
                "max": round(float(arr.max()), 4),
            }
            if arr.size >= 3 and correctness.size == arr.size and np.std(arr) > 0:
                rho = float(np.corrcoef(arr, correctness)[0, 1])
                if np.isfinite(rho):
                    stats[metric]["corr_correctness"] = round(rho, 4)

        result[step_key] = {"n_cases": len(case_ids), "stats": stats}

    return result
