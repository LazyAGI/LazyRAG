"""Evidence-extraction tools: per-case facts with step features."""

from __future__ import annotations

import time
from typing import Any

from lazyllm.tools import fc_register
from evo.domain.schemas import ErrorCode
from evo.tools._common import _ok, _fail
from evo.runtime.session import get_current_session


def _module_summary(mod: Any) -> dict[str, Any]:
    inp = str(mod.input)[:300] if mod.input else ""
    out = mod.output
    if isinstance(out, list):
        preview = f"[{len(out)} items]"
        if out and isinstance(out[0], dict):
            preview += f" first={dict(list(out[0].items())[:5])}"
    elif isinstance(out, str):
        preview = out[:300]
    else:
        preview = str(out)[:300] if out else ""
    return {"input_preview": inp, "output_preview": preview, "scores": mod.scores or []}


@fc_register("tool")
def export_case_evidence(dataset_id: str) -> str:
    """
    Export evidence bundle for one case: judge metrics, step IO summaries, step features.

    Args:
        dataset_id (str): Case dataset id.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No session.")
        judge = session._parsed_judge.get(dataset_id)
        if judge is None:
            return _fail(ErrorCode.CASE_NOT_FOUND.value, f"Not found: {dataset_id}")

        trace = session._parsed_trace.get(judge.trace_id)
        pipeline = session.trace_meta.pipeline or (list(trace.modules.keys()) if trace else [])

        metrics = {
            "answer_correctness": judge.answer_correctness,
            "context_recall": judge.context_recall,
            "doc_recall": judge.doc_recall,
            "faithfulness": judge.faithfulness,
            "key_hit_rate": len(judge.hit_key) / max(len(judge.key), 1),
        }

        cap = 500
        texts = {
            "query": (trace.query if trace else "")[:cap],
            "generated_answer": judge.generated_answer[:cap],
            "gt_answer": judge.gt_answer[:cap],
            "key_points": judge.key[:20],
            "hit_key": judge.hit_key[:20],
            "gt_file": judge.gt_file[:20],
            "retrieved_file": judge.retrieved_file[:20],
        }

        step_summaries = {n: _module_summary(trace.modules[n]) for n in pipeline if trace and n in trace.modules}
        step_feats = session.case_step_features.get(dataset_id, {})

        ev = {
            "dataset_id": dataset_id,
            "pipeline": pipeline,
            "judge_metrics": metrics,
            "judge_texts": texts,
            "step_summaries": step_summaries,
            "step_features": step_feats,
        }
        return _ok(ev, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))


@fc_register("tool")
def list_cases_ranked(score_field: str = "answer_correctness", order: str = "asc", limit: int = 10) -> str:
    """
    Rank loaded cases by a metric.

    Args:
        score_field (str): Judge metric field name.
        order (str): \"asc\" or \"desc\".
        limit (int): Max results.
    """
    start = time.time()
    try:
        session = get_current_session()
        if session is None or not session._parsed_judge:
            return _fail(ErrorCode.DATA_NOT_LOADED.value, "No data.")
        rows = []
        for did, j in session._parsed_judge.items():
            val = getattr(j, score_field, None)
            if val is not None:
                rows.append({"dataset_id": did, score_field: float(val)})
        rows.sort(key=lambda r: r[score_field], reverse=(order.lower() != "asc"))
        return _ok({"cases": rows[:limit], "total_loaded": len(session._parsed_judge)}, start)
    except Exception as e:
        return _fail(ErrorCode.INTERNAL_ERROR.value, str(e))
