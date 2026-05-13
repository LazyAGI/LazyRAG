from __future__ import annotations
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
import logging
from evo.datagen.validate import normalize_qa_json

_log = logging.getLogger('evo.datagen.writer')


def build_eval_report(eval_results: list[dict], eval_data: dict) -> dict[str, Any]:
    total = len(eval_results)
    answer_correctness_list: list[float] = []
    case_details: list[dict] = []
    for item in eval_results:
        case = dict(item)
        if 'evaluate_result' in case:
            eval_result = case.pop('evaluate_result')
            case.update(eval_result)
        case_details.append(case)
        if 'answer_correctness' in case:
            try:
                score = float(case['answer_correctness'])
                answer_correctness_list.append(score)
            except Exception:
                pass
    avg_score = (
        round(sum(answer_correctness_list) / len(answer_correctness_list), 4) if answer_correctness_list else 0.0
    )
    return {
        'report_id': str(uuid.uuid4()),
        'dataset_id': eval_data.get('eval_name', ''),
        'eval_name': eval_data.get('eval_name', ''),
        'eval_set_id': eval_data.get('eval_set_id', ''),
        'kb_id': eval_data.get('kb_id', ''),
        'total_cases': total,
        'avg_score': avg_score,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'case_details': case_details,
    }


def save_eval_report(eval_name: str, report: dict, base_dir: str | Path) -> str:
    result_dir = Path(base_dir) / 'datasets' / eval_name / 'results'
    result_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = result_dir / f'eval_report_{ts}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    _atomic_link_latest(result_dir, path)
    return str(path)


def _atomic_link_latest(result_dir: Path, path: Path) -> None:
    latest = result_dir / 'latest.json'
    tmp = result_dir / f'.latest.{os.getpid()}.tmp'
    try:
        if os.name == 'nt':
            if latest.exists():
                latest.unlink()
            os.link(str(path), str(latest))
        else:
            tmp.symlink_to(path.name)
            tmp.rename(latest)
    except Exception:
        pass
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def load_report(eval_name: str, base_dir: str | Path) -> dict[str, Any]:
    result_dir = Path(base_dir) / 'datasets' / eval_name / 'results'
    latest = result_dir / 'latest.json'
    if latest.exists():
        with open(latest, 'r', encoding='utf-8') as f:
            return json.load(f)
    files = sorted(result_dir.glob('eval_report_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f'no reports found for eval {eval_name}')
    with open(files[0], 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_eval_dir(eval_name: str, base_dir: str | Path) -> str:
    target = Path(base_dir) / 'datasets' / eval_name
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


def write_full_eval_set(eval_name: str, data: dict, base_dir: str | Path) -> str:
    folder = ensure_eval_dir(eval_name, base_dir)
    file_path = Path(folder) / 'eval_data.json'
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _log.info('eval set saved to %s', file_path)
    return str(file_path)


def extract_json(text: Any) -> dict:
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text)
    except Exception:
        if isinstance(text, str):
            match = re.search('\\{.*\\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    return {}
        return {}


def build_full_eval_set(qa_result: list[dict], eval_name: str, kb_id: str, task_id: str = '') -> dict[str, Any]:
    cases: list[dict] = []
    for item in qa_result:
        try:
            qa = normalize_qa_json(extract_json(item.get('qa', {})))
            if not qa:
                continue
            case = {
                'case_id': str(uuid.uuid4()),
                'reference_doc': qa.get('reference_doc', []),
                'reference_context': qa.get('reference_context', []),
                'is_deleted': False,
                'question': qa.get('question', ''),
                'question_type': qa.get('question_type', 1),
                'key_points': qa.get('key_points', []),
                'ground_truth': qa.get('ground_truth', ''),
                'generate_reason': qa.get('generate_reason', ''),
                'reference_chunk_ids': qa.get('reference_chunk_ids', []),
                'reference_doc_ids': qa.get('reference_doc_ids', []),
            }
            cases.append(case)
        except Exception:
            continue
    return {
        'eval_set_id': str(uuid.uuid4()),
        'eval_name': eval_name,
        'kb_id': kb_id,
        'task_id': task_id,
        'create_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_nums': len(cases),
        'cases': cases,
    }
