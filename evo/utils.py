from __future__ import annotations

import math
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

_CONFIDENCE_WORDS = {
    'low': 0.3, 'medium': 0.6, 'med': 0.6, 'mid': 0.6,
    'high': 0.85, 'very_high': 0.95, 'very high': 0.95,
}


def coerce_confidence(value: Any, default: float = 0.5) -> float:
    """Best-effort numeric coercion for LLM-emitted confidence fields."""
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        v = float(value)
    else:
        s = str(value).strip().lower()
        if not s:
            return default
        if s in _CONFIDENCE_WORDS:
            v = _CONFIDENCE_WORDS[s]
        else:
            try:
                v = float(s.rstrip('%')) / (100.0 if s.endswith('%') else 1.0)
            except ValueError:
                return default
    return max(0.0, min(1.0, v))


def safe_under(base: Path, user_path: str) -> Path:
    base = Path(base).resolve()
    if '..' in Path(user_path).parts:
        raise ValueError(f'Path traversal rejected: {user_path}')
    resolved = (base / user_path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(f'Path escapes base directory: {user_path}')
    return resolved


def jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return str(obj)


_THINK_RE = re.compile(r'<think>.*?</think>', flags=re.DOTALL)


def strip_thinking(text: str) -> str:
    return _THINK_RE.sub('', text).strip()


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    k = (n - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[int(f)] * (c - k) + sorted_values[int(c)] * (k - f)


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2:
        return None
    sx, sy = sum(x), sum(y)
    sxy = sum(a * b for a, b in zip(x, y))
    sx2 = sum(a * a for a in x)
    sy2 = sum(b * b for b in y)
    num = n * sxy - sx * sy
    dx = math.sqrt(max(n * sx2 - sx * sx, 0))
    dy = math.sqrt(max(n * sy2 - sy * sy, 0))
    if dx == 0 or dy == 0:
        return None
    return max(-1.0, min(1.0, num / (dx * dy)))
