"""Badcase clustering: global, per-step, and cross-step flow analysis."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from lazyllm.tools import fc_register
from sklearn.preprocessing import RobustScaler
from sklearn.decomposition import PCA

from evo.domain.schemas import ErrorCode
from evo.domain.step_features import flatten_case_features, build_step_matrix
from evo.runtime.session import get_current_session
from evo.tools._common import _ok, _fail

_CACHE_GLOBAL = "clustering"
_CACHE_PER_STEP = "clustering:per_step"
_CACHE_FLOW = "clustering:flow"


def _run_kmeans(X: np.ndarray) -> np.ndarray:
    """KMeans with silhouette-based k selection."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    n = X.shape[0]
    best_k, best_sc = 2, -1.0
    for k in range(2, min(11, n)):
        km = KMeans(n_clusters=k, n_init="auto", random_state=42).fit(X)
        sc = silhouette_score(X, km.labels_)
        if sc > best_sc:
            best_k, best_sc = k, sc
    return KMeans(n_clusters=best_k, n_init="auto", random_state=42).fit_predict(X)


def _run_clustering(mat: np.ndarray, method: str, min_cluster_size: int | None) -> np.ndarray:
    n = mat.shape[0]
    if n < 4:
        return np.zeros(n, dtype=int)
    X = RobustScaler().fit_transform(mat)
    if X.shape[1] > 30:
        X = PCA(n_components=min(30, n)).fit_transform(X)
    if method == "hdbscan":
        try:
            from hdbscan import HDBSCAN
            mcs = min_cluster_size or max(2, min(5, n // 2))
            labels = HDBSCAN(min_cluster_size=mcs).fit_predict(X)
            if (labels >= 0).sum() > 0:
                return labels
        except ImportError:
            pass
    return _run_kmeans(X)


def _build_cluster_summaries(ids, keys, mat, labels, score_field, session):
    global_mean = mat.mean(axis=0)
    global_std = mat.std(axis=0)
    global_std[global_std == 0] = 1.0
    summaries = []
    for lab in sorted(set(labels)):
        mask = labels == lab
        member_ids = [ids[i] for i in range(len(ids)) if mask[i]]
        sub = mat[mask]
        scores = []
        for did in member_ids:
            j = session._parsed_judge.get(did)
            val = getattr(j, score_field, None) if j else None
            if val is not None:
                scores.append(float(val))
        deltas = (sub.mean(axis=0) - global_mean) / global_std
        top_idx = np.argsort(np.abs(deltas))[::-1][:10]
        centroid = sub.mean(axis=0)
        dists = np.linalg.norm(sub - centroid, axis=1)
        exemplars = [member_ids[i] for i in np.argsort(dists)[:min(5, len(member_ids))]]

        # Group deltas by step prefix
        step_deltas: dict[str, dict[str, float]] = {}
        for i in top_idx:
            parts = keys[i].split(":", 1)
            step = parts[0] if len(parts) == 2 else "_global"
            metric = parts[1] if len(parts) == 2 else keys[i]
            step_deltas.setdefault(step, {})[metric] = round(float(deltas[i]), 3)

        summaries.append({
            "cluster_id": f"cluster_{lab}" if lab >= 0 else "noise",
            "size": int(mask.sum()),
            "score_stats": {"mean": round(float(np.mean(scores)), 4) if scores else None,
                            "min": round(float(min(scores)), 4) if scores else None,
                            "max": round(float(max(scores)), 4) if scores else None},
            "top_feature_deltas": {keys[i]: round(float(deltas[i]), 3) for i in top_idx},
            "step_grouped_deltas": step_deltas,
            "exemplar_case_ids": exemplars,
        })
    return summaries


# ---------------------------------------------------------------------------
# Tool: global clustering
# ---------------------------------------------------------------------------

@fc_register("tool")
def cluster_badcases(score_field: str = "answer_correctness", order: str = "asc",
                     limit: int = 500, method: str = "", min_cluster_size: int = 0) -> str:
    """
    Cluster badcases by step-level feature similarity.

    Args:
        score_field (str): Judge metric to rank cases.
        order (str): Sort order, \"asc\" or \"desc\".
        limit (int): Number of ranked cases to cluster.
        method (str): \"hdbscan\" or \"kmeans\" fallback.
        min_cluster_size (int): HDBSCAN param, 0=auto.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None or not session._parsed_judge:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No data.")
        method = method or session.config.cluster_method
        mcs = min_cluster_size or session.config.cluster_min_size

        rows = []
        for did, j in session._parsed_judge.items():
            val = getattr(j, score_field, None)
            if val is not None:
                rows.append((did, float(val)))
        rows.sort(key=lambda r: r[1], reverse=(order.lower() != "asc"))
        target = {r[0] for r in rows[:limit]}

        ids, frows = [], []
        for cid, sf in session.case_step_features.items():
            flat = flatten_case_features(sf)
            if flat:
                ids.append(cid)
                frows.append(flat)
        if not frows:
            return _fail(ErrorCode.INTERNAL_ERROR.value, "No features.")
        all_keys = sorted({k for r in frows for k in r})
        mat = np.array([[r.get(k, 0.0) for k in all_keys] for r in frows], dtype=np.float64)
        np.nan_to_num(mat, copy=False)

        keep = [i for i, cid in enumerate(ids) if cid in target]
        if not keep:
            return _fail(ErrorCode.INTERNAL_ERROR.value, "No features.")
        ids = [ids[i] for i in keep]
        mat = mat[keep]

        labels = _run_clustering(mat, method, mcs)
        summaries = _build_cluster_summaries(ids, all_keys, mat, labels, score_field, session)
        result = {
            "method": method, "n_cases": len(ids),
            "n_clusters": len([c for c in set(labels) if c >= 0]),
            "noise_count": int((labels == -1).sum()) if -1 in labels else 0,
            "cluster_summaries": summaries,
        }
        session.cache[_CACHE_GLOBAL] = result
        return _ok(result, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


# ---------------------------------------------------------------------------
# Tool: per-step clustering
# ---------------------------------------------------------------------------

@fc_register("tool")
def cluster_per_step(score_field: str = "answer_correctness", limit: int = 500,
                     method: str = "", min_cluster_size: int = 0) -> str:
    """
    Cluster cases independently at each pipeline step using that step's features only.

    Args:
        score_field (str): Judge metric for score stats.
        limit (int): Max cases to include.
        method (str): Clustering method.
        min_cluster_size (int): HDBSCAN param.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None or not session.case_step_features:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No data.")
        method = method or session.config.cluster_method
        mcs = min_cluster_size or session.config.cluster_min_size
        pipeline = session.trace_meta.pipeline

        # Rank and select target cases
        ranked = []
        for did, j in session._parsed_judge.items():
            val = getattr(j, score_field, None)
            if val is not None:
                ranked.append((did, float(val)))
        ranked.sort(key=lambda r: r[1])
        target_ids = {r[0] for r in ranked[:limit]}

        per_step: dict[str, Any] = {}
        for step_key in pipeline:
            ids, keys, mat = build_step_matrix(session.case_step_features, step_key, target_ids)
            if len(ids) < 4 or mat.shape[1] < 2:
                per_step[step_key] = {"n_cases": len(ids), "skipped": True}
                continue
            labels = _run_clustering(mat, method, mcs)
            sums = _build_cluster_summaries(ids, keys, mat, labels, score_field, session)
            per_step[step_key] = {
                "n_cases": len(ids),
                "n_clusters": len([c for c in set(labels) if c >= 0]),
                "cluster_summaries": sums,
                "labels": {cid: int(lab) for cid, lab in zip(ids, labels)},
            }

        session.cache[_CACHE_PER_STEP] = per_step
        overview = {k: {"n_cases": v["n_cases"], "n_clusters": v.get("n_clusters", 0),
                         "skipped": v.get("skipped", False)} for k, v in per_step.items()}
        return _ok({"pipeline": pipeline, "per_step": overview}, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


# ---------------------------------------------------------------------------
# Tool: cross-step flow analysis
# ---------------------------------------------------------------------------

def _entropy(labels: np.ndarray) -> float:
    _, counts = np.unique(labels, return_counts=True)
    p = counts / counts.sum()
    return float(-np.sum(p * np.log2(p + 1e-12)))


def _nmi(a: np.ndarray, b: np.ndarray) -> float:
    from sklearn.metrics import normalized_mutual_info_score
    return float(normalized_mutual_info_score(a, b))


@fc_register("tool")
def analyze_step_flow() -> str:
    """
    Analyze how case clusters change across adjacent pipeline steps.
    Requires cluster_per_step to have been run first.

    Detects convergence (cases consolidating), divergence (cases scattering),
    and stable transitions between steps.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No session.")
        per_step = session.cache.get(_CACHE_PER_STEP)
        if per_step is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "Run cluster_per_step first.")

        pipeline = session.trace_meta.pipeline
        # Build label arrays per step (aligned by case id)
        all_cids = sorted({cid for s in per_step.values() if "labels" in s for cid in s["labels"]})
        step_labels: dict[str, np.ndarray] = {}
        for sk in pipeline:
            info = per_step.get(sk, {})
            lmap = info.get("labels", {})
            if not lmap:
                continue
            step_labels[sk] = np.array([lmap.get(c, -1) for c in all_cids])

        active_steps = [s for s in pipeline if s in step_labels]
        transitions: list[dict[str, Any]] = []
        for i in range(len(active_steps) - 1):
            s_a, s_b = active_steps[i], active_steps[i + 1]
            la, lb = step_labels[s_a], step_labels[s_b]
            h_a, h_b = _entropy(la), _entropy(lb)
            delta_h = h_b - h_a
            nmi_val = _nmi(la, lb)

            if delta_h < -0.2:
                kind = "convergence"
            elif delta_h > 0.2 and nmi_val < 0.5:
                kind = "divergence"
            elif nmi_val > 0.7 and abs(delta_h) < 0.1:
                kind = "stable"
            else:
                kind = "shift"

            # Transition matrix
            unique_a, unique_b = sorted(set(la)), sorted(set(lb))
            tmat = np.zeros((len(unique_a), len(unique_b)), dtype=int)
            a_idx = {v: i for i, v in enumerate(unique_a)}
            b_idx = {v: i for i, v in enumerate(unique_b)}
            for ca, cb in zip(la, lb):
                tmat[a_idx[ca], b_idx[cb]] += 1

            transitions.append({
                "from_step": s_a, "to_step": s_b,
                "entropy_from": round(h_a, 3), "entropy_to": round(h_b, 3),
                "entropy_change": round(delta_h, 3),
                "nmi": round(nmi_val, 3), "type": kind,
                "transition_matrix": tmat.tolist(),
                "from_clusters": [f"cluster_{c}" for c in unique_a],
                "to_clusters": [f"cluster_{c}" for c in unique_b],
            })

        critical = [t["to_step"] for t in transitions if t["type"] in ("divergence", "convergence")]

        # Per-case label flow
        case_flow: dict[str, dict[str, str]] = {}
        for cid in all_cids[:50]:
            flow = {}
            for sk in active_steps:
                lab = per_step[sk]["labels"].get(cid)
                if lab is not None:
                    flow[sk] = f"cluster_{lab}" if lab >= 0 else "noise"
            case_flow[cid] = flow

        result = {
            "transition_analysis": transitions,
            "critical_steps": critical,
            "case_label_flow": case_flow,
        }
        session.cache[_CACHE_FLOW] = result
        return _ok(result, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


# ---------------------------------------------------------------------------
# Query tools
# ---------------------------------------------------------------------------

@fc_register("tool")
def get_cluster_summary(cluster_id: str, step_key: str = "") -> str:
    """
    Get one cluster summary from global or per-step clustering.

    Args:
        cluster_id (str): e.g. \"cluster_0\" or \"noise\".
        step_key (str): If provided, query per-step clustering for that step. Empty = global.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No session.")

        if step_key:
            per_step = session.cache.get(_CACHE_PER_STEP, {})
            info = per_step.get(step_key)
            if info is None or info.get("skipped"):
                return _fail(ErrorCode.CASE_NOT_FOUND.value,
                             f"No per-step clustering for {step_key}")
            summaries = info.get("cluster_summaries", [])
        else:
            cached = session.cache.get(_CACHE_GLOBAL)
            if cached is None:
                return _fail(ErrorCode.DATA_NOT_LOADED.value,
                             "Run cluster_badcases first.")
            summaries = cached.get("cluster_summaries", [])

        for cs in summaries:
            if cs["cluster_id"] == cluster_id:
                return _ok(cs, start)
        return _fail(ErrorCode.CASE_NOT_FOUND.value, f"Not found: {cluster_id}")
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


@fc_register("tool")
def list_cluster_exemplars(cluster_id: str, step_key: str = "", k: int = 5) -> str:
    """
    List exemplar case IDs for a cluster (global or per-step).

    Args:
        cluster_id (str): e.g. \"cluster_0\".
        step_key (str): If provided, query per-step clustering. Empty = global.
        k (int): Max exemplars.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No session.")

        if step_key:
            per_step = session.cache.get(_CACHE_PER_STEP, {})
            info = per_step.get(step_key, {})
            summaries = info.get("cluster_summaries", [])
        else:
            cached = session.cache.get(_CACHE_GLOBAL)
            summaries = cached.get("cluster_summaries", []) if cached else []

        for cs in summaries:
            if cs["cluster_id"] == cluster_id:
                return _ok({"cluster_id": cluster_id, "step_key": step_key or "global",
                             "exemplars": cs["exemplar_case_ids"][:k]}, start)
        return _fail(ErrorCode.CASE_NOT_FOUND.value, f"Not found: {cluster_id}")
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


@fc_register("tool")
def get_step_flow_analysis() -> str:
    """
    Return the cross-step flow analysis results.
    Requires analyze_step_flow to have been run first.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No session.")
        cached = session.cache.get(_CACHE_FLOW)
        if cached is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "Run analyze_step_flow first.")
        return _ok(cached, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))
