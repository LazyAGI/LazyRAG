from __future__ import annotations
from typing import Any
from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.session import get_current_session


def _module_summary(mod: Any) -> dict[str, Any]:
    inp = str(mod.input)[:300] if mod.input else ''
    out = mod.output
    if isinstance(out, list):
        preview = f'[{len(out)} items]'
        if out and isinstance(out[0], dict):
            preview += f' first={dict(list(out[0].items())[:5])}'
    elif isinstance(out, str):
        preview = out[:300]
    else:
        preview = str(out)[:300] if out else ''
    return {'input_preview': inp, 'output_preview': preview, 'scores': mod.scores or []}


def _summ_export(result: ToolResult[Any]) -> str:
    d = result.data or {}
    metrics = d.get('judge_metrics', {})
    return (
        f"case={d.get('dataset_id')} score={metrics.get('answer_correctness')} "
        f"hit_keys={len(d.get('judge_texts', {}).get('hit_key', []))}/"
        f"{len(d.get('judge_texts', {}).get('key_points', []))} "
        f"steps={list(d.get('step_summaries', {}).keys())}"
    )


@tool(tags=['evidence'], summarizer=_summ_export)
def export_case_evidence(dataset_id: str) -> ToolResult[dict[str, Any]]:
    if not dataset_id:
        return ToolResult.failure('export_case_evidence', ErrorCode.INVALID_ARGUMENT, 'dataset_id is required.')
    session = get_current_session()
    if session is None:
        return ToolResult.failure('export_case_evidence', ErrorCode.DATA_NOT_LOADED, 'No active session.')
    judge = session.get_judge(dataset_id)
    if judge is None:
        return ToolResult.failure(
            'export_case_evidence',
            ErrorCode.CASE_NOT_FOUND,
            f'Dataset ID not found: {dataset_id}. Use list_bad_cases() / list_cases_ranked() '
            f'to enumerate real IDs; examples: {session.sample_dataset_ids()}',
        )
    trace = session.get_trace(judge.trace_id)
    pipeline = session.trace_meta.pipeline or (list(trace.modules.keys()) if trace else [])
    metrics = {
        'answer_correctness': judge.answer_correctness,
        'context_recall': judge.context_recall,
        'doc_recall': judge.doc_recall,
        'faithfulness': judge.faithfulness,
        'key_hit_rate': len(judge.hit_key) / max(len(judge.key), 1),
    }
    cap = 500
    texts = {
        'query': (trace.query if trace else '')[:cap],
        'generated_answer': judge.generated_answer[:cap],
        'gt_answer': judge.gt_answer[:cap],
        'key_points': judge.key[:20],
        'hit_key': judge.hit_key[:20],
        'gt_file': judge.gt_file[:20],
        'retrieved_file': judge.retrieved_file[:20],
    }
    step_summaries = {n: _module_summary(trace.modules[n]) for n in pipeline if trace and n in trace.modules}
    step_feats = session.case_step_features.get(dataset_id, {})
    return ToolResult.success(
        'export_case_evidence',
        {
            'dataset_id': dataset_id,
            'pipeline': pipeline,
            'judge_metrics': metrics,
            'judge_texts': texts,
            'step_summaries': step_summaries,
            'step_features': step_feats,
        },
    )


def _summ_ranked(result: ToolResult[Any]) -> str:
    cases = (result.data or {}).get('cases', [])[:5]
    return f"top: {[(c.get('dataset_id'), list(c.values())[1]) for c in cases]}"


@tool(tags=['evidence'], summarizer=_summ_ranked)
def list_cases_ranked(
    score_field: str = 'answer_correctness', order: str = 'asc', limit: int = 10
) -> ToolResult[dict[str, Any]]:
    if order.lower() not in ('asc', 'desc'):
        return ToolResult.failure('list_cases_ranked', ErrorCode.INVALID_ARGUMENT, "order must be 'asc' or 'desc'.")
    if limit < 1:
        return ToolResult.failure('list_cases_ranked', ErrorCode.INVALID_ARGUMENT, 'limit must be >= 1.')
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('list_cases_ranked', ErrorCode.DATA_NOT_LOADED, 'Judge corpus not loaded.')
    rows: list[dict[str, Any]] = []
    for did, j in session.iter_judge():
        val = getattr(j, score_field, None)
        if val is None:
            continue
        rows.append({'dataset_id': did, score_field: float(val)})
    rows.sort(key=lambda r: r[score_field], reverse=order.lower() != 'asc')
    return ToolResult.success('list_cases_ranked', {'cases': rows[:limit], 'total_loaded': len(session.parsed_judge)})
