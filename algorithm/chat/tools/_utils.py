from __future__ import annotations

import json
from typing import Any, Dict


def truncate_text(text: Any, max_len: int) -> str:
    if text is None:
        return ''
    raw = text if isinstance(text, str) else str(text)
    return raw if len(raw) <= max_len else f'{raw[:max_len]}...'


def parse_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def absolute_url(url: str) -> str:
    normalized = str(url or '').strip()
    if not normalized:
        return ''
    if normalized.startswith(('http://', 'https://')):
        return normalized
    return f'https://{normalized}'
