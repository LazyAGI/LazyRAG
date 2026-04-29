from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from evo.service.core import store as _store
from evo.service.threads.workspace import ThreadWorkspace


def build_results_router(*, base_dir: Path, store: _store.FsStateStore) -> APIRouter:
    router = APIRouter(prefix='/v1/evo/threads/{thread_id}/results',
                       tags=['thread-results'])

    @router.get('/datasets')
    def datasets(thread_id: str) -> list[dict]:
        ws = _ws(base_dir, thread_id)
        dataset_ids = list(ws.load_artifacts().get('dataset_ids') or [])
        for row in _store.list_flow_tasks_by_thread(store, 'eval', thread_id):
            dataset_id = (row.get('payload') or {}).get('dataset_id')
            if dataset_id and dataset_id not in dataset_ids:
                dataset_ids.append(dataset_id)
        out = []
        for dataset_id in dataset_ids:
            path = Path(base_dir) / 'datasets' / dataset_id / 'eval_data.json'
            data = _read_json(path) or {}
            out.append({
                'dataset_id': dataset_id,
                'path': str(path),
                'exists': path.is_file(),
                'case_count': len(data.get('cases') or []),
                'kb_id': data.get('kb_id'),
            })
        return out

    @router.get('/eval-reports')
    def eval_reports(thread_id: str) -> list[dict]:
        ws = _ws(base_dir, thread_id)
        out = []
        for path in sorted((ws.dir / 'evals').glob('*.json')):
            data = _read_json(path) or {}
            out.append({
                'eval_id': path.stem,
                'path': str(path),
                'report_id': data.get('report_id'),
                'total_cases': data.get('total_cases'),
                'metrics': data.get('metrics') or data.get('summary'),
            })
        return out

    @router.get('/analysis-reports')
    def analysis_reports(thread_id: str) -> list[dict]:
        ws = _ws(base_dir, thread_id)
        reports_dir = ws.dir / 'outputs' / 'reports'
        out = []
        for row in _store.list_flow_tasks_by_thread(store, 'run', thread_id):
            report_id = (row.get('payload') or {}).get('report_id')
            if not report_id:
                continue
            json_path = _first_existing(
                reports_dir / f'{report_id}.json',
                Path(base_dir) / 'work' / 'reports' / f'{report_id}.json',
                Path(base_dir) / 'reports' / f'{report_id}.json',
            )
            md_path = _first_existing(
                reports_dir / f'{report_id}.md',
                Path(base_dir) / 'work' / 'reports' / f'{report_id}.md',
                Path(base_dir) / 'reports' / f'{report_id}.md',
            )
            out.append({
                'run_id': row['id'],
                'report_id': report_id,
                'json_path': str(json_path),
                'md_path': str(md_path),
                'json': _read_json(json_path),
                'markdown': _read_text(md_path),
            })
        return out

    @router.get('/diffs')
    def diffs(thread_id: str) -> list[dict]:
        ws = _ws(base_dir, thread_id)
        out = []
        for row in _store.list_flow_tasks_by_thread(store, 'apply', thread_id):
            apply_id = row['id']
            preview = _preview_index_path(base_dir, ws, apply_id)
            preview_data = _read_json(preview) or {}
            out.append({
                'apply_id': apply_id,
                'status': row.get('status'),
                'preview_path': str(preview) if preview.is_file() else None,
                'preview': preview_data or None,
                'files': _diff_files(preview_data),
            })
        return out

    @router.get('/abtests')
    def abtests(thread_id: str) -> list[dict]:
        ws = _ws(base_dir, thread_id)
        out = []
        for abtest_id in ws.load_artifacts().get('abtest_ids') or []:
            d = ws.dir / 'abtests' / abtest_id
            out.append({
                'abtest_id': abtest_id,
                'summary': _read_json(d / 'summary.json'),
                'decision': _read_json(d / 'decision.json'),
                'markdown': _read_text(d / 'summary.md'),
            })
        return out

    return router


def _ws(base_dir: Path, thread_id: str) -> ThreadWorkspace:
    ws = ThreadWorkspace(base_dir, thread_id, create=False)
    if not ws.thread_meta_path.exists():
        raise HTTPException(404, f'thread {thread_id} not found')
    return ws


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    return paths[0]


def _preview_index_path(base_dir: Path, ws: ThreadWorkspace,
                        apply_id: str) -> Path:
    preview_rel = Path('applies') / apply_id / 'preview' / apply_id / 'index.json'
    legacy_rel = Path('applies') / apply_id / 'preview' / 'index.json'
    return _first_existing(
        ws.dir / 'outputs' / preview_rel,
        Path(base_dir) / 'work' / preview_rel,
        ws.dir / 'outputs' / legacy_rel,
        Path(base_dir) / 'work' / legacy_rel,
    )


def _diff_files(preview: dict) -> list[dict]:
    out: list[dict] = []
    for item in preview.get('files') or []:
        if not isinstance(item, dict):
            continue
        path = Path(str(item.get('diff_path') or ''))
        out.append({
            'path': item.get('path'),
            'change_kind': item.get('change_kind'),
            'additions': item.get('additions'),
            'deletions': item.get('deletions'),
            'diff_path': str(path) if str(path) else None,
            'filename': path.name if path.name else None,
            'content': _read_text(path) if path.is_file() else None,
        })
    return out
