from __future__ import annotations

from typing import Any

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.session import get_current_session


_MAX_FIELD_LENGTH = 500


_EXPANDABLE_FIELDS = {'generated_answer', 'gt_answer', 'retrieved_text', 'gt_text'}


@tool(tags=['inspect'])
def get_case_detail(
    dataset_id: str,
    step_filter: str | None = None,
    expand_field: str | None = None,
) -> ToolResult[dict[str, Any]]:
    """Two-mode case inspection.

    - default: judge + first 5 trace modules (each input/output capped at 500 chars).
    - ``step_filter=<step_key>``: only that step's full input/output (no truncation).
    - ``expand_field=<name>``: return that judge field full text. Valid names:
      ``generated_answer | gt_answer | retrieved_text | gt_text``.
    """
    if not dataset_id or not isinstance(dataset_id, str):
        return ToolResult.failure('get_case_detail', ErrorCode.INVALID_ARGUMENT,
                                  'dataset_id must be a non-empty string')
    if expand_field is not None and expand_field not in _EXPANDABLE_FIELDS:
        return ToolResult.failure(
            'get_case_detail', ErrorCode.INVALID_ARGUMENT,
            f'expand_field must be one of {sorted(_EXPANDABLE_FIELDS)}, got {expand_field!r}',
        )
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('get_case_detail', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')
    try:
        merged = session.get_merged_case(dataset_id)
    except KeyError:
        return ToolResult.failure('get_case_detail', ErrorCode.CASE_NOT_FOUND,
                                  f'Dataset ID not found: {dataset_id}')
    except ValueError as exc:
        return ToolResult.failure('get_case_detail', ErrorCode.TRACE_NOT_FOUND, str(exc))

    if step_filter is not None:
        module = merged.trace.modules.get(step_filter)
        if module is None:
            return ToolResult.failure(
                'get_case_detail', ErrorCode.INVALID_ARGUMENT,
                f'step_filter {step_filter!r} not in trace; available: '
                f'{list(merged.trace.modules.keys())}',
            )
        return ToolResult.success('get_case_detail', {
            'dataset_id': merged.dataset_id,
            'step_key': step_filter,
            'input': module.input,
            'output': module.output,
        })

    if expand_field is not None:
        value = getattr(merged.judge, expand_field)
        return ToolResult.success('get_case_detail', {
            'dataset_id': merged.dataset_id,
            'field': expand_field,
            'value': value,
            'length': (len(value) if isinstance(value, (str, list)) else None),
        })

    truncated_fields: dict[str, Any] = {}
    generated = merged.judge.generated_answer
    if len(generated) > _MAX_FIELD_LENGTH:
        truncated_fields['judge.generated_answer'] = {
            'truncated': True, 'excerpt': generated[:_MAX_FIELD_LENGTH] + '...',
            'full_length': len(generated),
        }
    gt = merged.judge.gt_answer
    if len(gt) > _MAX_FIELD_LENGTH:
        truncated_fields['judge.gt_answer'] = {
            'truncated': True, 'excerpt': gt[:_MAX_FIELD_LENGTH] + '...',
            'full_length': len(gt),
        }

    return ToolResult.success('get_case_detail', {
        'dataset_id': merged.dataset_id,
        'query': merged.query,
        'judge': {
            'trace_id': merged.judge.trace_id,
            'answer_correctness': merged.judge.answer_correctness,
            'key': merged.judge.key,
            'hit_key': merged.judge.hit_key,
            'reason': merged.judge.reason,
            'context_recall': merged.judge.context_recall,
            'doc_recall': merged.judge.doc_recall,
            'retrieved_file': merged.judge.retrieved_file,
            'gt_file': merged.judge.gt_file,
            'retrieved_text': merged.judge.retrieved_text[:3],
            'gt_text': merged.judge.gt_text[:3],
            'generated_answer': generated[:_MAX_FIELD_LENGTH],
            'gt_answer': gt[:_MAX_FIELD_LENGTH],
            'faithfulness': merged.judge.faithfulness,
            'human_verified': merged.judge.human_verified,
        },
        'trace': {
            'query': merged.trace.query,
            'pipeline': session.trace_meta.pipeline,
            'modules': {
                k: {
                    'input': str(v.input)[:_MAX_FIELD_LENGTH],
                    'output': (str(v.output)[:_MAX_FIELD_LENGTH] if v.output else None),
                }
                for k, v in list(merged.trace.modules.items())[:5]
            },
        },
        'truncation_info': truncated_fields,
    })


@tool(tags=['inspect'])
def inspect_step_for_case(dataset_id: str, step_key: str) -> ToolResult[dict[str, Any]]:
    """Full input/output for ONE step in ONE case (no truncation).

    Use after ``summarize_step_metrics`` or ``get_case_detail`` flags a
    suspicious (case, step). Pairs the raw module IO with this case's
    step-level features so you can correlate observation with metric.
    """
    if not dataset_id or not isinstance(dataset_id, str):
        return ToolResult.failure('inspect_step_for_case', ErrorCode.INVALID_ARGUMENT,
                                  'dataset_id must be a non-empty string')
    if not step_key or not isinstance(step_key, str):
        return ToolResult.failure('inspect_step_for_case', ErrorCode.INVALID_ARGUMENT,
                                  'step_key must be a non-empty string')
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('inspect_step_for_case', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')
    try:
        merged = session.get_merged_case(dataset_id)
    except KeyError:
        return ToolResult.failure('inspect_step_for_case', ErrorCode.CASE_NOT_FOUND,
                                  f'Dataset ID not found: {dataset_id}')
    except ValueError as exc:
        return ToolResult.failure('inspect_step_for_case', ErrorCode.TRACE_NOT_FOUND, str(exc))

    module = merged.trace.modules.get(step_key)
    if module is None:
        return ToolResult.failure(
            'inspect_step_for_case', ErrorCode.INVALID_ARGUMENT,
            f'step_key {step_key!r} not present in trace; available: '
            f'{list(merged.trace.modules.keys())}',
        )

    feats = session.case_step_features.get(dataset_id, {}).get(step_key, {})
    return ToolResult.success('inspect_step_for_case', {
        'dataset_id': dataset_id,
        'step_key': step_key,
        'input': module.input,        # untruncated
        'output': module.output,      # untruncated
        'step_features': feats,
        'judge_score': merged.judge.answer_correctness,
        'pipeline': list(session.trace_meta.pipeline),
    })


@tool(tags=['inspect'])
def list_bad_cases(
    threshold: float = 0.6,
    score_field: str | None = None,
    limit: int = 10,
    offset: int = 0,
    sort: str = 'asc',
) -> ToolResult[dict[str, Any]]:
    """List paginated bad cases with a score histogram."""
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('list_bad_cases', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')
    if sort not in ('asc', 'desc'):
        return ToolResult.failure('list_bad_cases', ErrorCode.INVALID_ARGUMENT,
                                  "sort must be 'asc' or 'desc'")
    if limit < 1 or limit > 100:
        return ToolResult.failure('list_bad_cases', ErrorCode.INVALID_ARGUMENT,
                                  'limit must be between 1 and 100')
    if offset < 0:
        return ToolResult.failure('list_bad_cases', ErrorCode.INVALID_ARGUMENT,
                                  'offset must be non-negative')

    metric = score_field or session.config.badcase_score_field

    all_cases: list[dict[str, Any]] = []
    for did, j in session.iter_judge():
        score = getattr(j, metric, None)
        if not isinstance(score, (int, float)) or score >= threshold:
            continue
        trace = session.get_trace(j.trace_id)
        all_cases.append({
            'dataset_id': did,
            'score': score,
            'trace_id': j.trace_id,
            'query_preview': trace.query if trace else None,
        })
    all_cases.sort(key=lambda x: x['score'], reverse=(sort == 'desc'))

    buckets = {k: 0 for k in ('0.0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0')}
    for case in all_cases:
        s = case['score']
        if s < 0.2:
            buckets['0.0-0.2'] += 1
        elif s < 0.4:
            buckets['0.2-0.4'] += 1
        elif s < 0.6:
            buckets['0.4-0.6'] += 1
        elif s < 0.8:
            buckets['0.6-0.8'] += 1
        else:
            buckets['0.8-1.0'] += 1

    page = all_cases[offset: offset + limit]
    next_offset = offset + limit if offset + limit < len(all_cases) else None

    return ToolResult.success('list_bad_cases', {
        'total_count': len(all_cases),
        'cases': page,
        'next_offset': next_offset,
        'histogram': buckets,
        'threshold': threshold,
        'score_field': metric,
    })


@tool(tags=['inspect'])
def compare_cases(dataset_id1: str, dataset_id2: str) -> ToolResult[dict[str, Any]]:
    """Symmetric metric and pipeline diff between two cases."""
    if not dataset_id1 or not dataset_id2:
        return ToolResult.failure('compare_cases', ErrorCode.INVALID_ARGUMENT,
                                  'Both dataset IDs required.')
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('compare_cases', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')
    try:
        case1 = session.get_merged_case(dataset_id1)
        case2 = session.get_merged_case(dataset_id2)
    except KeyError as exc:
        return ToolResult.failure('compare_cases', ErrorCode.CASE_NOT_FOUND, str(exc))

    metrics_to_compare = ['answer_correctness', 'context_recall', 'doc_recall', 'faithfulness']
    metrics_diff: dict[str, Any] = {}
    for m in metrics_to_compare:
        v1 = getattr(case1.judge, m, None)
        v2 = getattr(case2.judge, m, None)
        if v1 is None or v2 is None:
            continue
        diff = v1 - v2
        metrics_diff[m] = {
            'case1': v1, 'case2': v2, 'diff': diff,
            'better': 'case1' if diff > 0 else ('case2' if diff < 0 else 'equal'),
        }

    ppl_meta = session.trace_meta.pipeline or list(case1.trace.modules.keys())
    ppl2 = session.trace_meta.pipeline or list(case2.trace.modules.keys())
    pipeline_diff = {
        'case1_pipeline': ppl_meta,
        'case2_pipeline': ppl2,
        'length_diff': len(ppl_meta) - len(ppl2),
        'common_modules': list(set(ppl_meta) & set(ppl2)),
        'unique_to_case1': list(set(ppl_meta) - set(ppl2)),
        'unique_to_case2': list(set(ppl2) - set(ppl_meta)),
    }
    module_diff = {
        'case1_module_count': len(case1.trace.modules),
        'case2_module_count': len(case2.trace.modules),
        'common_module_names': list(
            set(case1.trace.modules) & set(case2.trace.modules)
        ),
    }

    hints: list[str] = []
    ac = metrics_diff.get('answer_correctness')
    if ac and ac['diff']:
        hints.append(
            f"{'case1' if ac['better']=='case1' else 'case2'} has higher correctness; "
            'examine its retrieval and generation pipeline for transferable patterns.'
        )
    if pipeline_diff['length_diff']:
        longer = 'case1' if pipeline_diff['length_diff'] > 0 else 'case2'
        hints.append(f'{longer} has longer pipeline; verify whether extra modules help.')

    return ToolResult.success('compare_cases', {
        'dataset_id1': dataset_id1,
        'dataset_id2': dataset_id2,
        'metrics_diff': metrics_diff,
        'pipeline_diff': pipeline_diff,
        'module_diff': module_diff,
        'hypothesis_hints': hints,
    })


@tool(tags=['inspect'])
def list_dataset_ids(
    min_score: float | None = None,
    max_score: float | None = None,
) -> ToolResult[dict[str, Any]]:
    """Enumerate dataset IDs with optional score filters."""
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('list_dataset_ids', ErrorCode.DATA_NOT_LOADED,
                                  'Judge corpus not loaded.')
    metric = session.config.badcase_score_field
    rows: list[dict[str, Any]] = []
    for did, j in session.iter_judge():
        score = getattr(j, metric, None)
        if score is None:
            continue
        if min_score is not None and score < min_score:
            continue
        if max_score is not None and score >= max_score:
            continue
        rows.append({'dataset_id': did, 'score': score})
    rows.sort(key=lambda x: x['score'])

    return ToolResult.success('list_dataset_ids', {
        'total_count': len(rows),
        'ids': rows,
        'filters': {'min_score': min_score, 'max_score': max_score, 'score_field': metric},
    })


@tool(tags=['inspect'])
def get_session_status() -> ToolResult[dict[str, Any]]:
    """Describe the active session: run_id, loaded counts, completed stages."""
    session = get_current_session()
    if session is None:
        return ToolResult.failure('get_session_status', ErrorCode.DATA_NOT_LOADED,
                                  'No active session.')
    return ToolResult.success('get_session_status', {
        'run_id': session.run_id,
        'created_at': session.created_at.isoformat(),
        'judge_loaded': bool(session.parsed_judge),
        'trace_loaded': bool(session.parsed_trace),
        'judge_case_count': len(session.parsed_judge),
        'trace_case_count': len(session.parsed_trace),
        'stages_completed': sorted(session.stages_completed),
        'config_paths': {
            'data_dir': str(session.config.data_dir),
            'output_dir': str(session.config.output_dir),
            'judge_path': str(session.config.default_judge_path),
            'trace_path': str(session.config.default_trace_path),
        },
    })


@tool(tags=['inspect'])
def recall_handle(handle: str) -> ToolResult[dict[str, Any]]:
    """Look up the raw result of a previous tool call by its handle id."""
    session = get_current_session()
    if session is None or session.handle_store is None:
        return ToolResult.failure('recall_handle', ErrorCode.DATA_NOT_LOADED,
                                  'no handle store on session')
    h = session.handle_store.get(handle)
    if h is None:
        return ToolResult.failure('recall_handle', ErrorCode.INVALID_ARGUMENT,
                                  f'unknown handle {handle!r}')
    return ToolResult.success('recall_handle', {
        'tool': h.tool, 'args': h.args, 'result': h.result,
    })
