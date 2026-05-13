"""Phase 3 tests for Indexer agent + briefing investigation_seeds.

Run: PYTHONPATH=. .venv/bin/python -m evo.tests.test_indexer
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Callable
from unittest.mock import MagicMock, patch

from evo.agents.indexer import _append_hypotheses, _build_input, run_indexer
from evo.conductor.world_model import WorldModel
from evo.harness import analysis as analysis_steps, data_loader
from evo.runtime.config import load_config
from evo.runtime.session import create_session, session_scope
from evo.tools import register_all


def _h(name: str) -> None:
    print(f"\n=== {name} ===")


def _bootstrap_session():
    register_all()
    session = create_session(load_config())
    with session_scope(session):
        data_loader.load_corpus(session)
        analysis_steps.compute_step_features(session)
        analysis_steps.cluster_global(session, badcase_limit=5,
                                      score_field="answer_correctness")
        analysis_steps.cluster_per_step(session, badcase_limit=5,
                                        score_field="answer_correctness")
        analysis_steps.analyze_flow(session)
    return session


def test_build_input_has_required_sections() -> None:
    _h("Indexer _build_input contains pipeline + step_metrics + clusters + flow")
    session = _bootstrap_session()
    payload = _build_input(session)
    assert {"pipeline", "step_metrics", "clusters", "flow", "metric_directions",
            "avg_judge", "total_cases"}.issubset(payload.keys())
    assert payload["total_cases"] == len(session.parsed_judge)
    assert payload["pipeline"] == list(session.trace_meta.pipeline)
    print(f"  step_metrics steps={list(payload['step_metrics'].keys())}")
    print("  -> OK")


def test_append_hypotheses_dedupes_by_id() -> None:
    _h("_append_hypotheses skips duplicate ids and assigns sequential fallback")
    world = WorldModel(run_id="r1")
    _append_hypotheses(world, [
        {"id": "H1", "claim": "a", "category": "c", "confidence": 0.5},
        {"claim": "auto-id", "confidence": 0.7},
        {"id": "H1", "claim": "dup", "confidence": 0.9},
    ])
    assert len(world.hypotheses) == 2
    assert {h.id for h in world.hypotheses} == {"H1", "H002"}
    assert world.hypotheses[0].source == "indexer"
    print("  -> OK")


def test_run_indexer_writes_world_model_and_telemetry() -> None:
    _h("run_indexer parses LLM JSON and writes to WorldModel")
    session = _bootstrap_session()
    fake_llm_output = json.dumps({
        "hypotheses": [
            {"id": "H1", "claim": "rerank drops gt", "category": "rerank_failure",
             "confidence": 0.85, "supporting_metrics": ["chunk_recall_delta"],
             "investigation_paths": ["调 inspect_step_for_case"]},
            {"id": "H2", "claim": "low overlap", "category": "generation_drift",
             "confidence": 0.6, "supporting_metrics": ["answer_gt_overlap"],
             "investigation_paths": ["调 export_case_evidence"]},
        ],
        "cross_step_narrative": "Retriever ok, reranker bad.",
        "open_questions": ["why answer_correctness high?"],
    })
    with session_scope(session):
        with patch("evo.agents.indexer.LLMInvoker") as MockInvoker:
            MockInvoker.return_value.invoke.return_value = fake_llm_output
            result = run_indexer(session)
    assert len(result["hypotheses"]) == 2
    world = session.world_store.world
    assert len(world.hypotheses) == 2
    assert {h.id for h in world.hypotheses} == {"H1", "H2"}
    assert world.hypotheses[0].source == "indexer"
    print(f"  world.hypotheses ids: {[h.id for h in world.hypotheses]}")
    print("  -> OK")


def test_run_indexer_handles_parse_failure() -> None:
    _h("run_indexer with non-JSON output writes nothing")
    session = _bootstrap_session()
    with session_scope(session):
        with patch("evo.agents.indexer.LLMInvoker") as MockInvoker:
            MockInvoker.return_value.invoke.return_value = "not a json"
            result = run_indexer(session)
    assert result == {}
    assert session.world_store.world.hypotheses == []
    print("  -> OK")


def test_run_indexer_idempotent() -> None:
    _h("run_indexer with cached LLM result does not duplicate hypotheses")
    session = _bootstrap_session()
    fake = json.dumps({
        "hypotheses": [
            {"id": "H1", "claim": "x", "category": "y", "confidence": 0.5,
             "investigation_paths": []},
        ],
        "cross_step_narrative": "", "open_questions": [],
    })
    with session_scope(session):
        with patch("evo.agents.indexer.LLMInvoker") as MockInvoker:
            MockInvoker.return_value.invoke.return_value = fake
            run_indexer(session)
            run_indexer(session)
    assert len(session.world_store.world.hypotheses) == 1
    print("  -> OK")


def _run(tests: list[Callable[[], None]]) -> int:
    failures = 0
    for t in tests:
        try:
            t()
        except Exception:
            failures += 1
            print(f"FAILED: {t.__name__}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


def main() -> int:
    return _run([
        test_build_input_has_required_sections,
        test_append_hypotheses_dedupes_by_id,
        test_run_indexer_writes_world_model_and_telemetry,
        test_run_indexer_handles_parse_failure,
        test_run_indexer_idempotent,
    ])


if __name__ == "__main__":
    sys.exit(main())
