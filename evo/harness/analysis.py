from __future__ import annotations

import hashlib
import logging

import numpy as np

from evo.domain.step_features import aggregate_global_step_analysis, build_case_step_features
from evo.runtime.session import AnalysisSession

_log = logging.getLogger("evo.harness.analysis")


def _make_session_embed_fn(session: AnalysisSession):
    if session.embed is None or session.embed_provider is None:
        return None

    def embed(text: str) -> 'np.ndarray | None':
        cache_key = hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]

        def _produce() -> np.ndarray:
            return np.asarray(session.embed_provider()(text),
                                dtype=np.float64).ravel()
        return session.embed.call(producer=_produce, cache_key=cache_key)
    return embed


def compute_step_features(session: AnalysisSession) -> int:
    pipeline = session.trace_meta.pipeline
    resolver = session.resolve_node
    embed_fn = _make_session_embed_fn(session)
    features: dict = {}
    for cid, j in session.iter_judge():
        trace = session.get_trace(j.trace_id)
        if trace is None:
            continue
        features[cid] = build_case_step_features(j, trace, pipeline, resolver,
                                                    embed_fn=embed_fn)
    global_analysis = aggregate_global_step_analysis(features, session.parsed_judge, pipeline)
    session.set_step_features(features, global_analysis)
    _log.info("Step features: %d cases, %d steps", len(features), len(pipeline))
    return len(features)


def cluster_global(session: AnalysisSession, *, badcase_limit: int, score_field: str) -> int:
    from evo.harness.clustering import cluster_badcases
    result = cluster_badcases(score_field=score_field, limit=badcase_limit).unwrap()
    session.set_clustering_global(result)
    _log.info("Global clustering: %d cases -> %d clusters", result.n_cases, result.n_clusters)
    return result.n_clusters


def cluster_per_step(session: AnalysisSession, *, badcase_limit: int, score_field: str) -> int:
    from evo.harness.clustering import cluster_per_step as _impl
    result = _impl(score_field=score_field, limit=badcase_limit).unwrap()
    session.set_clustering_per_step(result)
    active = [k for k, v in result.per_step.items() if not v.skipped]
    _log.info("Per-step clustering: %d active steps", len(active))
    return len(active)


def analyze_flow(session: AnalysisSession) -> int:
    if session.clustering_per_step is None:
        _log.info("Skipping flow analysis (per-step clustering missing)")
        return 0
    from evo.harness.clustering import analyze_step_flow
    result = analyze_step_flow().unwrap()
    session.set_flow_analysis(result)
    _log.info("Flow analysis: %d transitions, critical=%s",
              len(result.transition_analysis), result.critical_steps)
    return len(result.transition_analysis)


def collect_exemplar_ids(session: AnalysisSession, *, max_ids: int = 40) -> list[str]:
    cg = session.clustering_global
    if cg is None:
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for cs in cg.cluster_summaries:
        for eid in cs.exemplar_case_ids:
            if eid not in seen:
                seen.add(eid)
                ids.append(eid)
                if len(ids) >= max_ids:
                    return ids
    return ids
