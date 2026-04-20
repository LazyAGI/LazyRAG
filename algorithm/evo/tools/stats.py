'''Corpus-level statistics tools (numerics live in :mod:`evo.utils`).'''

from __future__ import annotations

import math
from typing import Any

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.session import get_current_session
from evo.utils import kendall, partial_correlation, pearson, percentile, spearman

_METRICS = ('answer_correctness', 'context_recall', 'doc_recall', 'faithfulness')


def _summ_metrics(result: ToolResult[Any]) -> str:
    d = result.data or {}
    metrics = d.get('metrics', {})
    means = {m: round(v['mean'], 3) for m, v in metrics.items()
             if isinstance(v, dict) and v.get('mean') is not None}
    return f"n={d.get('total_cases')} means={means}"


@tool(tags=['stats'], summarizer=_summ_metrics)
def summarize_metrics(case_ids: list[str] | None = None) -> ToolResult[dict[str, Any]]:
    """Summarise metric distributions across the corpus or a subset."""
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('summarize_metrics', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')
    if case_ids is not None:
        if not isinstance(case_ids, list):
            return ToolResult.failure('summarize_metrics', ErrorCode.INVALID_ARGUMENT,
                                      'case_ids must be a list or None.')
        if len(case_ids) == 0:
            return ToolResult.failure('summarize_metrics', ErrorCode.INVALID_ARGUMENT,
                                      'case_ids cannot be empty (use None for all cases).')

    target_ids = case_ids if case_ids is not None else session.list_dataset_ids()

    values: dict[str, list[float]] = {m: [] for m in _METRICS}
    missing: dict[str, int] = {m: 0 for m in _METRICS}

    for did in target_ids:
        j = session.get_judge(did)
        if j is None:
            continue
        for m in _METRICS:
            v = getattr(j, m, None)
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                missing[m] += 1
                continue
            try:
                values[m].append(float(v))
            except (TypeError, ValueError):
                missing[m] += 1

    summary: dict[str, Any] = {}
    for m in _METRICS:
        vs = sorted(values[m])
        if not vs:
            summary[m] = {
                'mean': None, 'median': None, 'min': None, 'max': None,
                'p10': None, 'p90': None, 'count': 0, 'missing_count': missing[m],
            }
            continue
        summary[m] = {
            'mean': round(sum(vs) / len(vs), 4),
            'median': round(percentile(vs, 50), 4),
            'min': round(min(vs), 4),
            'max': round(max(vs), 4),
            'p10': round(percentile(vs, 10), 4),
            'p90': round(percentile(vs, 90), 4),
            'count': len(vs),
            'missing_count': missing[m],
        }

    total_keys = total_hits = 0
    hit_rates: list[float] = []
    for did in target_ids:
        j = session.get_judge(did)
        if j is None:
            continue
        total = len(j.key)
        total_keys += total
        hit = len(j.hit_key)
        total_hits += hit
        if total > 0:
            hit_rates.append(hit / total)
    key_hit_stats = {
        'total_keys': total_keys,
        'total_hit_keys': total_hits,
        'avg_hit_rate': round(sum(hit_rates) / len(hit_rates), 4) if hit_rates else 0.0,
    }

    return ToolResult.success('summarize_metrics', {
        'metrics': summary,
        'key_hit_stats': key_hit_stats,
        'total_cases': len(target_ids),
        'filtered': case_ids is not None,
    })


def _summ_step_metrics(result: ToolResult[Any]) -> str:
    """Highlight the worst (step, metric) pair to seed agent attention."""
    by_step = (result.data or {}).get('by_step', {})
    worst_step = worst_metric = None
    worst_mean: float | None = None
    for step, body in by_step.items():
        for m, v in body.get('metrics', {}).items():
            if not isinstance(v, dict) or 'mean' not in v:
                continue
            mean = v['mean']
            if worst_mean is None or mean < worst_mean:
                worst_mean, worst_step, worst_metric = mean, step, m
    steps = list(by_step.keys())[:6]
    if worst_step is not None:
        return f'steps={steps}; lowest mean: {worst_step}.{worst_metric}={worst_mean}'
    return f'steps={steps}'


@tool(tags=['stats'], summarizer=_summ_step_metrics)
def summarize_step_metrics(
    step_key: str | None = None,
    case_ids: list[str] | None = None,
    metric: str | None = None,
) -> ToolResult[dict[str, Any]]:
    """Step-level feature distribution. No anomaly judgment — pure stats.

    - ``step_key=None``: cover all pipeline steps; specified: focus one step.
    - ``case_ids=None``: full corpus; specified: subset.
    - ``metric=None``: every metric for the step; specified: single metric.

    Returned per (step, metric): mean / std / min / max / p10 / p90 / count.
    """
    session = get_current_session()
    if session is None or not session.case_step_features:
        return ToolResult.failure('summarize_step_metrics', ErrorCode.DATA_NOT_LOADED,
                                  'Step features not computed (run features step first).')
    if case_ids is not None:
        if not isinstance(case_ids, list) or not case_ids:
            return ToolResult.failure('summarize_step_metrics', ErrorCode.INVALID_ARGUMENT,
                                      'case_ids must be a non-empty list or None.')

    pipeline = list(session.trace_meta.pipeline)
    if step_key is not None:
        if step_key not in pipeline:
            return ToolResult.failure(
                'summarize_step_metrics', ErrorCode.INVALID_ARGUMENT,
                f'step_key {step_key!r} not in pipeline {pipeline}',
            )
        target_steps = [step_key]
    else:
        target_steps = pipeline

    target_cases = case_ids if case_ids is not None else list(session.case_step_features.keys())

    out: dict[str, Any] = {}
    for step in target_steps:
        vectors: dict[str, list[float]] = {}
        for cid in target_cases:
            sf = session.case_step_features.get(cid, {}).get(step, {})
            for m, v in sf.items():
                if metric is not None and m != metric:
                    continue
                if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                    continue
                vectors.setdefault(m, []).append(float(v))
        per_metric: dict[str, Any] = {}
        for m, vals in vectors.items():
            vs = sorted(vals)
            per_metric[m] = {
                'mean': round(sum(vs) / len(vs), 4),
                'std': round((sum((x - sum(vs) / len(vs)) ** 2 for x in vs) / len(vs)) ** 0.5, 4),
                'min': round(vs[0], 4),
                'max': round(vs[-1], 4),
                'p10': round(percentile(vs, 10), 4),
                'p90': round(percentile(vs, 90), 4),
                'count': len(vs),
            }
        n_with_step = sum(1 for cid in target_cases
                          if step in session.case_step_features.get(cid, {}))
        out[step] = {'n_cases_with_data': n_with_step, 'metrics': per_metric}

    return ToolResult.success('summarize_step_metrics', {
        'pipeline': pipeline,
        'scope': {
            'step_key': step_key,
            'metric': metric,
            'case_ids_subset': case_ids is not None,
            'n_cases_examined': len(target_cases),
        },
        'by_step': out,
    })


def _strength(r: float | None) -> str:
    if r is None:
        return 'N/A'
    a = abs(r)
    if a >= 0.8: return 'very_strong'
    if a >= 0.6: return 'strong'
    if a >= 0.4: return 'moderate'
    if a >= 0.2: return 'weak'
    return 'negligible'


def _collect_vectors(session: Any, ids: list[str], metrics: tuple[str, ...]) -> dict[str, list[float]]:
    data: dict[str, list[float]] = {m: [] for m in metrics}
    for did in ids:
        j = session.get_judge(did)
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


@tool(tags=['stats'])
def correlate_metrics_enhanced(
    case_ids: list[str] | None = None,
    methods: list[str] | None = None,
    control_variables: list[str] | None = None,
) -> ToolResult[dict[str, Any]]:
    """Multi-method correlation (pearson/spearman/kendall/partial) with consensus."""
    valid = {'pearson', 'spearman', 'kendall', 'partial'}
    if methods is None:
        methods = ['pearson', 'spearman', 'kendall']
    unknown = set(methods) - valid
    if unknown:
        return ToolResult.failure('correlate_metrics_enhanced', ErrorCode.INVALID_ARGUMENT,
                                  f'Unknown methods: {sorted(unknown)}; valid={sorted(valid)}')
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('correlate_metrics_enhanced', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')

    target_ids = case_ids if case_ids is not None else session.list_dataset_ids()
    data = _collect_vectors(session, target_ids, _METRICS)
    n = len(data[_METRICS[0]])

    warnings: list[str] = []
    if n < 3:
        warnings.append(f'Only {n} complete cases; correlations are unreliable')
    elif n < 10:
        warnings.append(f'Small sample ({n} cases); interpret with caution')

    results: dict[str, Any] = {}
    fns = {'pearson': pearson, 'spearman': spearman, 'kendall': kendall}
    for method in methods:
        if method == 'partial':
            if not control_variables:
                results['partial'] = {'note': 'Specify control_variables to compute partial correlations'}
                continue
            missing_ctrl = [c for c in control_variables if c not in data]
            if missing_ctrl:
                results['partial'] = {'error': f'Control variables not found: {missing_ctrl}'}
                continue
            ctrl_vecs = [data[c] for c in control_variables]
            analyse = [m for m in _METRICS if m not in control_variables]
            matrix: dict[str, Any] = {}
            for i, m1 in enumerate(analyse):
                for m2 in analyse[i + 1:]:
                    r = partial_correlation(data[m1], data[m2], ctrl_vecs)
                    matrix[f'{m1}_vs_{m2}_ctrl_{'_'.join(control_variables)}'] = {
                        'coefficient': round(r, 4) if r is not None else None,
                        'strength': _strength(r), 'sample_size': n,
                        'controlled_for': control_variables,
                    }
            results['partial'] = matrix
            continue

        fn = fns[method]
        matrix = {}
        for i, m1 in enumerate(_METRICS):
            for m2 in _METRICS[i + 1:]:
                r = fn(data[m1], data[m2])
                matrix[f'{m1}_vs_{m2}'] = {
                    'coefficient': round(r, 4) if r is not None else None,
                    'strength': _strength(r), 'sample_size': n,
                }
        results[method] = matrix

    return ToolResult.success('correlate_metrics_enhanced', {
        'methods_used': methods,
        'results': results,
        'consensus': _consensus(results),
        'sample_size': n,
        'warnings': warnings,
    })


@tool(tags=['stats'])
def correlate_metrics(case_ids: list[str] | None = None) -> ToolResult[dict[str, Any]]:
    """Simple Pearson-only correlations between key metrics."""
    return correlate_metrics_enhanced(case_ids=case_ids, methods=['pearson'])


def _consensus(results: dict[str, Any]) -> dict[str, Any]:
    pair_scores: dict[str, list[float]] = {}
    for method, matrix in results.items():
        if not isinstance(matrix, dict):
            continue
        for key, val in matrix.items():
            if not isinstance(val, dict):
                continue
            coef = val.get('coefficient')
            if coef is not None:
                pair_scores.setdefault(key, []).append(coef)

    out: dict[str, Any] = {}
    for pair, scores in pair_scores.items():
        strong = [s for s in scores if abs(s) >= 0.4]
        if len(strong) < 2:
            continue
        directions = [1 if s > 0 else -1 for s in strong]
        if len(set(directions)) != 1:
            continue
        out[pair] = {
            'methods_agreeing': len(strong),
            'mean_coefficient': round(sum(strong) / len(strong), 4),
            'direction': 'positive' if directions[0] > 0 else 'negative',
            'strength': _strength(sum(strong) / len(strong)),
            'confidence': 'high' if len(strong) >= 3 else 'medium',
        }
    return out
