from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from evo.runtime.fs import atomic_write_json
from evo.service.core import store as _store
from evo.service.threads.results import build_results_router
from evo.service.threads.workspace import ThreadWorkspace


def test_abtest_results_return_eval_report_rows(tmp_path):
    base_dir = tmp_path / "evo"
    store = _store.FsStateStore(base_dir / "state")
    thread_id = "thr-1"
    ws = ThreadWorkspace(base_dir, thread_id)
    atomic_write_json(ws.thread_meta_path, {"thread_id": thread_id})
    ws.attach_artifact("abtest_ids", "abtest-1")

    eval_id = "eval-candidate-1"
    atomic_write_json(
        ws.eval_path(eval_id),
        {
            "report_id": "report-1",
            "total_cases": 1,
            "case_details": [{"case_id": "case-1", "question_type": 1}],
        },
    )
    decision_path = ws.abtest_dir("abtest-1") / "decision.json"
    atomic_write_json(decision_path, {"new_eval_id": eval_id})

    app = FastAPI()
    app.include_router(build_results_router(base_dir=base_dir, store=store))

    response = TestClient(app).get(f"/v1/evo/threads/{thread_id}/results/abtests")

    assert response.status_code == 200
    assert response.json() == [
        {
            "eval_id": eval_id,
            "path": str(ws.eval_path(eval_id)),
            "report_id": "report-1",
            "total_cases": 1,
            "metrics": None,
        }
    ]
