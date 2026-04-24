from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path


class MockEvalProvider:
    def __init__(self, fixture_path: Path | str) -> None:
        self._data = json.loads(Path(fixture_path).read_text(encoding='utf-8'))

    def get_eval_report(self, eval_id: str) -> dict:
        return self._data

    def list_evals(self, *, kb_id: str | None = None) -> list[dict]:
        r = self._data
        return [{
            'eval_id': str(r.get('report_id', 'mock-1')),
            'eval_set_id': r.get('eval_set_id'),
            'kb_id': r.get('kb_id'),
            'kb_name': r.get('kb_name'),
            'total_cases': r.get('total_cases'),
            'avg_score': r.get('avg_score'),
        }]

    def run_eval(self, *, dataset_id: str, target_chat_url: str,
                 options: dict | None = None) -> dict:
        report = copy.deepcopy(self._data)
        report['report_id'] = f'mock-{uuid.uuid4().hex[:8]}'
        report.setdefault('metadata', {}).update(
            {'dataset_id': dataset_id, 'target_chat_url': target_chat_url})
        return report
