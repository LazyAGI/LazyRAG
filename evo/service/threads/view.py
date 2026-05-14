from __future__ import annotations

import json
from pathlib import Path

from evo.orchestrator import capabilities as caps
from evo.orchestrator.planner import PlanContext
from evo.service.core import state as thread_state
from evo.service.core import store
from evo.service.threads.workspace import ThreadWorkspace


class ThreadView:
    def __init__(self, *, base_dir: Path, store_: store.FsStateStore) -> None:
        self.base_dir = base_dir
        self.store = store_

    def list_threads(self) -> list[dict]:
        base = self.base_dir / 'state' / 'threads'
        if not base.exists():
            return []
        return [row for path in sorted(base.glob('*/thread.json')) if (row := thread_state.read_json(path))]

    def get_thread(self, thread_id: str) -> dict | None:
        ws = ThreadWorkspace(self.base_dir, thread_id, create=False)
        meta = thread_state.read_json(ws.thread_meta_path)
        if meta is None:
            return None
        checkpoint = ws.load_checkpoint()
        meta['artifacts'] = self.artifacts(thread_id, ws)
        meta['pending_checkpoints'] = [checkpoint] if checkpoint else []
        return meta

    def statuses(self) -> dict:
        threads = []
        counts: dict[str, int] = {}
        for meta in self.list_threads():
            tid = str(meta.get('id') or '')
            if not tid:
                continue
            item = {
                **self.flow_status(tid),
                'title': meta.get('title') or '',
                'mode': meta.get('mode') or 'interactive',
                'created_at': meta.get('created_at'),
                'updated_at': meta.get('updated_at'),
            }
            threads.append(item)
            counts[item['status']] = counts.get(item['status'], 0) + 1
        threads.sort(key=lambda row: row.get('updated_at') or row.get('created_at') or 0.0, reverse=True)
        return {'total': len(threads), 'counts': counts, 'threads': threads}

    def flow_status(self, thread_id: str) -> dict:
        ws = ThreadWorkspace(self.base_dir, thread_id, create=False)
        if not ws.thread_meta_path.exists():
            return {'thread_id': thread_id, 'status': 'not_found'}
        rows = self.task_rows(thread_id, ws.load_artifacts())
        record = thread_state.load_thread(self.base_dir, thread_id, rows)
        report_ready = self._abtest_report_ready(ws, thread_state.latest_task(rows, 'abtest'))
        return thread_state.project_flow_status(record, rows, report_ready)

    def planner_context(self, thread_id: str, messages_path: Path, artifacts: dict) -> PlanContext:
        snapshot = self.snapshot(thread_id, artifacts)
        return PlanContext(
            thread_id=thread_id,
            recent_history=_read_recent_messages(messages_path),
            thread_state_summary=self.summary(snapshot),
            capabilities_with_safety=[
                {'op': op, 'safety': caps.get(op).safety, 'flow': caps.get(op).flow} for op in caps.all_ops()
            ],
            thread_state=snapshot,
        )

    def snapshot(self, thread_id: str, artifacts: dict) -> dict:
        rows = self.task_rows(thread_id, artifacts)
        latest = {flow: row for flow in store.FLOWS if (row := thread_state.latest_task(rows, flow))}
        active = [row for row in rows if thread_state.is_task_executing(row)]
        ws = ThreadWorkspace(self.base_dir, thread_id, create=False)
        checkpoint = ws.load_checkpoint()
        return {
            'inputs': _thread_inputs(ws),
            'artifacts': self.artifacts(thread_id, ws, rows, artifacts),
            'active_tasks': active,
            'latest_tasks': latest,
            'pending_checkpoint': checkpoint,
            'pending_checkpoints': [checkpoint] if checkpoint else [],
        }

    def artifacts(
        self,
        thread_id: str,
        ws: ThreadWorkspace | None = None,
        rows: list[dict] | None = None,
        raw: dict | None = None,
    ) -> dict:
        ws = ws or ThreadWorkspace(self.base_dir, thread_id, create=False)
        rows = rows if rows is not None else self.task_rows(thread_id, raw or ws.load_artifacts())
        data = dict(raw or ws.load_artifacts())
        data['dataset_ids'] = _real_dataset_ids(self.base_dir, data, rows)
        return data

    def summary(self, snapshot: dict) -> str:
        parts = [_format_artifacts(snapshot.get('artifacts') or {})]
        inputs = snapshot.get('inputs') or {}
        if inputs:
            parts.append('thread_inputs: ' + json.dumps(inputs, ensure_ascii=False)[:2000])
        latest = snapshot.get('latest_tasks') or {}
        if latest:
            compact = {k: {'id': v.get('id'), 'status': v.get('status'), 'payload': v.get('payload')}
                       for k, v in latest.items()}
            parts.append('latest_tasks: ' + json.dumps(compact, ensure_ascii=False)[:4000])
        active = snapshot.get('active_tasks') or []
        if active:
            parts.append('active_tasks: ' + ', '.join(f"{r['flow']}:{r['id']}:{r['status']}" for r in active[-10:]))
        return '\n'.join(part for part in parts if part)

    def task_rows(self, thread_id: str, artifacts: dict | None = None) -> list[dict]:
        rows = []
        seen: set[str] = set()
        for flow in store.FLOWS:
            for row in store.list_flow_tasks_by_thread(self.store, flow, thread_id):
                rows.append(row)
                seen.add(str(row.get('id')))
        for kind in ('run_ids', 'apply_ids', 'abtest_ids'):
            for task_id in (artifacts or {}).get(kind) or []:
                if task_id in seen:
                    continue
                row = store.get(self.store, task_id)
                if row and row.get('thread_id') == thread_id:
                    rows.append(row)
                    seen.add(task_id)
        rows.sort(key=lambda row: row.get('created_at', 0.0))
        return rows

    @staticmethod
    def _abtest_report_ready(ws: ThreadWorkspace, row: dict | None) -> bool:
        if not row:
            return False
        out_dir = ws.dir / 'abtests' / row['id']
        return (out_dir / 'summary.md').exists() and (out_dir / 'summary.json').exists()


def _thread_inputs(ws: ThreadWorkspace) -> dict:
    meta = thread_state.read_json(ws.thread_meta_path) or {}
    return meta.get('inputs') or {}


def _real_dataset_ids(base_dir: Path, artifacts: dict, rows: list[dict]) -> list[str]:
    ids: list[str] = []

    def add(dataset_id: str | None) -> None:
        if dataset_id and dataset_id not in ids and (base_dir / 'datasets' / dataset_id / 'eval_data.json').is_file():
            ids.append(dataset_id)

    for dataset_id in artifacts.get('dataset_ids') or []:
        add(str(dataset_id))
    for row in rows:
        if row.get('flow') != 'dataset_gen':
            continue
        payload = row.get('payload') or {}
        add(payload.get('eval_name'))
    return ids


def _format_artifacts(artifacts: dict) -> str:
    parts = []
    for kind in ('dataset_ids', 'eval_ids', 'run_ids', 'apply_ids', 'apply_commit_ids', 'abtest_ids', 'chat_ids'):
        vals = artifacts.get(kind) or []
        if vals:
            parts.append(f"{kind}: {', '.join(vals[-3:])}")
    return '\n'.join(parts)


def _read_recent_messages(path: Path, limit: int = 20) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines()[-limit:]:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append((str(obj.get('role', '')), str(obj.get('content', ''))))
    return rows
