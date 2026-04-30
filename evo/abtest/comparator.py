from __future__ import annotations
from dataclasses import dataclass
from math import comb
from statistics import mean
from typing import Iterable
DEFAULT_METRICS: tuple[str, ...] = ('answer_correctness', 'context_recall', 'doc_recall', 'faithfulness')
@dataclass(frozen=True)
class VerdictPolicy:
    primary_metric: str = 'answer_correctness'
    eps: float = 0.01
    p_value: float = 0.05
    guard_metrics: tuple[str, ...] = ('doc_recall', 'context_recall')
    guard_eps: float = 0.02
def _key(case: dict) -> str:
    return str(case.get('case_id') or case.get('query') or '')
def _index_cases(report: dict) -> dict[str, dict]:
    return {k: case for case in report.get('case_details') or [] if (k := _key(case))}
def _scores(cases: Iterable[dict], metric: str) -> list[float]:
    return [float(v) for c in cases if isinstance((v := c.get(metric)), (int, float))]
def _sign_test_p(diffs: list[float]) -> float | None:
    nonzero = [d for d in diffs if d != 0]
    n = len(nonzero)
    if n < 6:
        return None
    pos = sum((1 for d in nonzero if d > 0))
    k = max(pos, n - pos)
    total = 2 ** n
    upper = sum((comb(n, i) for i in range(k, n + 1)))
    lower = sum((comb(n, i) for i in range(0, n - k + 1)))
    return min(1.0, (upper + lower) / total)
_EMPTY_DIFF = {'mean_a': None, 'mean_b': None, 'delta_mean': None, 'win_rate_b': None, 'sign_p': None, 'n': 0}
def _metric_diff(a: list[float], b: list[float]) -> dict:
    if not a or not b:
        return dict(_EMPTY_DIFF)
    n = min(len(a), len(b))
    (a, b) = (a[:n], b[:n])
    diffs = [bv - av for (av, bv) in zip(a, b)]
    return {'mean_a': round(mean(a), 6), 'mean_b': round(mean(b), 6), 'delta_mean': round(mean(diffs), 6), 'win_rate_b': round(sum((d > 0 for d in diffs)) / n, 6), 'sign_p': _sign_test_p(diffs), 'n': n}
def compare_evals(report_a: dict, report_b: dict, *, metrics: Iterable[str]=DEFAULT_METRICS, top_k: int=5, primary_metric: str='answer_correctness') -> dict:
    (idx_a, idx_b) = (_index_cases(report_a), _index_cases(report_b))
    aligned = sorted(set(idx_a) & set(idx_b))
    if not aligned:
        return {'aligned_cases': 0, 'unique_to_a': sorted(set(idx_a) - set(idx_b))[:top_k], 'unique_to_b': sorted(set(idx_b) - set(idx_a))[:top_k], 'metrics': {}, 'missing_metrics': list(metrics), 'top_diff_cases': [], 'invalid_reason': 'No aligned cases found between baseline and candidate reports. Check that case_ids match and both reports have case_details.'}
    a_cases = [idx_a[k] for k in aligned]
    b_cases = [idx_b[k] for k in aligned]
    metric_diffs = {}
    missing_metrics = []
    for m in metrics:
        a_scores = _scores(a_cases, m)
        b_scores = _scores(b_cases, m)
        if not a_scores or not b_scores:
            missing_metrics.append(m)
            continue
        metric_diffs[m] = _metric_diff(a_scores, b_scores)
    deltas = []
    for k in aligned:
        (av, bv) = (idx_a[k].get(primary_metric), idx_b[k].get(primary_metric))
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
            deltas.append((k, round(float(bv) - float(av), 6), float(av), float(bv)))
    deltas.sort(key=lambda x: abs(x[1]), reverse=True)
    return {'aligned_cases': len(aligned), 'unique_to_a': sorted(set(idx_a) - set(idx_b))[:top_k], 'unique_to_b': sorted(set(idx_b) - set(idx_a))[:top_k], 'metrics': metric_diffs, 'missing_metrics': missing_metrics, 'top_diff_cases': [{'case_key': k, 'delta': d, 'a': a, 'b': b} for (k, d, a, b) in deltas[:top_k]]}
def judge_verdict(summary: dict, policy: VerdictPolicy=VerdictPolicy()) -> dict:
    if summary.get('aligned_cases', 0) == 0:
        return {'verdict': 'invalid', 'reasons': [summary.get('invalid_reason', 'aligned_cases=0, cannot judge')], 'policy': policy.__dict__}
    metrics = summary.get('metrics') or {}
    policy_dict = policy.__dict__
    for m in policy.guard_metrics:
        d = (metrics.get(m) or {}).get('delta_mean')
        if isinstance(d, (int, float)) and d <= -policy.guard_eps:
            return {'verdict': 'regressed', 'reasons': [f'{m} Δmean={d} (guard {policy.guard_eps})'], 'policy': policy_dict}
    pm = metrics.get(policy.primary_metric) or {}
    delta = pm.get('delta_mean')
    p = pm.get('sign_p')
    sig = p is None or (isinstance(p, (int, float)) and p < policy.p_value)
    if isinstance(delta, (int, float)) and sig:
        if delta >= policy.eps:
            return {'verdict': 'improved', 'reasons': [f'{policy.primary_metric} Δmean={delta} (p={p})'], 'policy': policy_dict}
        if delta <= -policy.eps:
            return {'verdict': 'regressed', 'reasons': [f'{policy.primary_metric} Δmean={delta} (p={p})'], 'policy': policy_dict}
    return {'verdict': 'inconclusive', 'reasons': [f'{policy.primary_metric} Δmean={delta} p={p}'], 'policy': policy_dict}
