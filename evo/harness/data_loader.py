from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any
from evo.domain import JudgeRecord, LoadSummary, TraceMeta, TraceRecord
from evo.domain.models import parse_eval_report, parse_judge_record, parse_trace_file
from evo.runtime.session import AnalysisSession

_log = logging.getLogger('evo.harness.loader')


def _load_judges(raw_judge: Any) -> tuple[dict[str, JudgeRecord], dict[str, Any] | None, list[str]]:
    if isinstance(raw_judge, dict) and isinstance(raw_judge.get('case_details'), list):
        judges, meta, warns = parse_eval_report(raw_judge)
        return (judges, meta, warns)
    judges: dict[str, JudgeRecord] = {}
    warnings: list[str] = []
    for did, payload in raw_judge.items():
        if did == 'count':
            continue
        try:
            rec, warns = parse_judge_record(payload)
            judges[did] = rec
            warnings.extend((f'[{did}] {w}' for w in warns))
        except ValueError as exc:
            warnings.append(f'[{did}] {exc}')
    return (judges, None, warnings)


def _load_traces(trace_path: Path) -> tuple[TraceMeta, dict[str, TraceRecord], list[str]]:
    if not trace_path.exists():
        return (TraceMeta(), {}, [])
    raw_trace = json.loads(trace_path.read_text(encoding='utf-8'))
    return parse_trace_file(raw_trace)


def load_corpus(
    session: AnalysisSession, judge_path: Path | None = None, trace_path: Path | None = None
) -> LoadSummary:
    jp = Path(judge_path or session.config.default_judge_path)
    if not jp.exists():
        raise FileNotFoundError(f'Judge file not found: {jp}')
    raw_judge = json.loads(jp.read_text(encoding='utf-8'))
    judges, eval_meta, warnings = _load_judges(raw_judge)
    tp = Path(trace_path or session.config.default_trace_path)
    trace_meta, traces, trace_warns = _load_traces(tp)
    warnings.extend(trace_warns)
    if not traces and judges:
        _log.warning('Trace file not found or empty (%s); pipeline step analysis disabled', tp)
        warnings.append(f'No trace loaded from {tp}; step-level analysis will be skipped.')
    trace_missing = [f'{did}->{j.trace_id}' for (did, j) in judges.items() if traces and j.trace_id not in traces]
    if trace_missing:
        warnings.append(f'{len(trace_missing)} judge cases have no matching trace')
    session.set_parsed_corpus(
        judges=judges, traces=traces, trace_meta=trace_meta, warnings=warnings, eval_report_meta=eval_meta
    )
    return LoadSummary(
        total_cases=len(judges),
        field_histogram={},
        sample_keys=list(judges)[:5],
        warnings=warnings[:],
        missing_traces=trace_missing or None,
    )
