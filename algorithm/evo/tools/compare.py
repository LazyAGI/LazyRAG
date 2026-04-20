from __future__ import annotations

from collections import defaultdict
from typing import Any

from evo.domain.tool_result import ErrorCode, ToolResult
from evo.harness.registry import tool
from evo.runtime.session import get_current_session


@tool(tags=['compare'])
def evaluate_dataset_quality(case_ids: list[str]) -> ToolResult[dict[str, Any]]:
    """Inspect eval-set data quality issues."""
    if not case_ids:
        return ToolResult.failure('evaluate_dataset_quality', ErrorCode.INVALID_ARGUMENT,
                                  'empty case_ids')
    session = get_current_session()
    if session is None or not session.parsed_judge:
        return ToolResult.failure('evaluate_dataset_quality', ErrorCode.DATA_NOT_LOADED,
                                  'No data.')

    issues: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for did in case_ids:
        j = session.get_judge(did)
        if j is None:
            continue
        if not j.generated_answer or len(j.generated_answer.strip()) < 10:
            issues.append({'case_id': did, 'issue_type': 'empty_or_short_answer',
                           'signals': {'len': len(j.generated_answer or '')}})
            counts['empty_or_short_answer'] += 1
        if j.key and len(j.key) != len(set(j.key)):
            issues.append({'case_id': did, 'issue_type': 'duplicate_keys',
                           'signals': {'total': len(j.key), 'unique': len(set(j.key))}})
            counts['duplicate_keys'] += 1
        if session.parsed_trace and j.trace_id not in session.parsed_trace:
            issues.append({'case_id': did, 'issue_type': 'missing_trace',
                           'signals': {'trace_id': j.trace_id}})
            counts['missing_trace'] += 1
        if not j.gt_file and not j.gt_text:
            issues.append({'case_id': did, 'issue_type': 'missing_gt', 'signals': {}})
            counts['missing_gt'] += 1
    return ToolResult.success('evaluate_dataset_quality', {
        'issues': issues,
        'summary': dict(counts),
        'total_checked': len(case_ids),
    })
