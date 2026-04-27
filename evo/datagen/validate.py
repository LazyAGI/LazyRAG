from __future__ import annotations

import json


def is_qa_json_valid(qa_json) -> bool:
    if not isinstance(qa_json, dict):
        return False
    for value in qa_json.values():
        if value is None:
            return False
        if isinstance(value, str) and len(value.strip()) == 0:
            return False
    return True


def safe_parse_qa_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip().replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(text)
    except Exception:
        return None
