from __future__ import annotations
from typing import Any
from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.session import get_current_session
@tool(tags=['cluster'])
def get_cluster_summary(cluster_id: str, step_key: str='') -> ToolResult[dict[str, Any]]:
    session = get_current_session()
    if session is None:
        return ToolResult.failure('get_cluster_summary', ErrorCode.DATA_NOT_LOADED, 'No session.')
    if step_key:
        per = session.clustering_per_step
        if per is None or step_key not in per.per_step:
            return ToolResult.failure('get_cluster_summary', ErrorCode.CASE_NOT_FOUND, f'No per-step clustering for {step_key}')
        summaries = per.per_step[step_key].cluster_summaries
    else:
        cg = session.clustering_global
        if cg is None:
            return ToolResult.failure('get_cluster_summary', ErrorCode.DATA_NOT_LOADED, 'Global clustering not available.')
        summaries = cg.cluster_summaries
    for cs in summaries:
        if cs.cluster_id == cluster_id:
            return ToolResult.success('get_cluster_summary', {'cluster_id': cs.cluster_id, 'size': cs.size, 'score_stats': cs.score_stats, 'top_feature_deltas': cs.top_feature_deltas, 'step_grouped_deltas': cs.step_grouped_deltas, 'exemplar_case_ids': cs.exemplar_case_ids})
    return ToolResult.failure('get_cluster_summary', ErrorCode.CASE_NOT_FOUND, f'Not found: {cluster_id}')
@tool(tags=['cluster'])
def list_cluster_exemplars(cluster_id: str, step_key: str='', k: int=5) -> ToolResult[dict[str, Any]]:
    if k < 1:
        return ToolResult.failure('list_cluster_exemplars', ErrorCode.INVALID_ARGUMENT, 'k must be >= 1')
    session = get_current_session()
    if session is None:
        return ToolResult.failure('list_cluster_exemplars', ErrorCode.DATA_NOT_LOADED, 'No session.')
    if step_key:
        per = session.clustering_per_step
        summaries = per.per_step[step_key].cluster_summaries if per and step_key in per.per_step else []
    else:
        cg = session.clustering_global
        summaries = cg.cluster_summaries if cg else []
    for cs in summaries:
        if cs.cluster_id == cluster_id:
            return ToolResult.success('list_cluster_exemplars', {'cluster_id': cluster_id, 'step_key': step_key or 'global', 'exemplars': cs.exemplar_case_ids[:k]})
    return ToolResult.failure('list_cluster_exemplars', ErrorCode.CASE_NOT_FOUND, f'Not found: {cluster_id}')
def _summ_flow(result: ToolResult[Any]) -> str:
    d = result.data or {}
    transitions = d.get('transition_analysis', [])
    interesting = [f"{t['from_step']}->{t['to_step']}({t['type']})" for t in transitions if t.get('type') != 'stable'][:5]
    return f"critical={d.get('critical_steps', [])}; transitions: {interesting}"
@tool(tags=['cluster'], summarizer=_summ_flow)
def get_step_flow_analysis() -> ToolResult[dict[str, Any]]:
    session = get_current_session()
    if session is None:
        return ToolResult.failure('get_step_flow_analysis', ErrorCode.DATA_NOT_LOADED, 'No session.')
    flow = session.flow_analysis
    if flow is None:
        return ToolResult.failure('get_step_flow_analysis', ErrorCode.DATA_NOT_LOADED, 'Flow analysis not available.')
    return ToolResult.success('get_step_flow_analysis', {'transition_analysis': [t.__dict__ for t in flow.transition_analysis], 'critical_steps': flow.critical_steps, 'case_label_flow': flow.case_label_flow})
