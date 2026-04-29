from __future__ import annotations

import json
import re
from typing import Any


def is_qa_json_valid(qa_json) -> bool:
    return normalize_qa_json(qa_json) is not None


def normalize_qa_json(qa_json: Any) -> dict[str, Any] | None:
    if not isinstance(qa_json, dict):
        return None
    qa = dict(qa_json)
    if 'query' in qa and 'question' not in qa:
        qa['question'] = qa.pop('query')
    if 'answer' in qa and 'ground_truth' not in qa:
        qa['ground_truth'] = qa.pop('answer')
    for key in ('reference_context', 'reference_doc', 'key_points',
                'reference_doc_ids', 'reference_chunk_ids'):
        if key in qa:
            qa[key] = _as_list(qa[key])
    if not _text(qa.get('question')) or not _text(qa.get('ground_truth')):
        return None
    if not _nonempty_text_list(qa.get('key_points')):
        qa['key_points'] = _key_points_from_answer(qa['ground_truth'])
    if not _nonempty_text_list(qa.get('key_points')):
        return None
    if 'question_type' in qa:
        try:
            qa['question_type'] = int(qa['question_type'])
        except Exception:
            return None
    for value in qa.values():
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, list) and any(
            v is None or (isinstance(v, str) and not v.strip()) for v in value
        ):
            return None
    return qa


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value]
    return []


def _nonempty_text_list(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(v, str) and v.strip() for v in value)


def _key_points_from_answer(answer: str) -> list[str]:
    parts = re.split(r'[，,；;。\n]+', str(answer).strip())
    return [p.strip() for p in parts if p.strip()][:5]


def require_valid_eval_case(case: dict[str, Any]) -> None:
    if not isinstance(case, dict):
        raise ValueError('eval case must be a dict')
    missing = [
        key for key in ('case_id', 'question', 'ground_truth', 'key_points')
        if not case.get(key)
    ]
    if missing:
        raise ValueError(f'eval case {case.get("case_id") or "<unknown>"} missing {missing}')
    if not isinstance(case.get('key_points'), list):
        raise ValueError(f'eval case {case.get("case_id")} key_points must be a list')
    if not str(case.get('question')).strip() or not str(case.get('ground_truth')).strip():
        raise ValueError(f'eval case {case.get("case_id")} has empty question or ground_truth')


def safe_parse_qa_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip().replace('```json', '').replace('```', '').strip()
    try:
        return normalize_qa_json(json.loads(text))
    except Exception:
        return None
