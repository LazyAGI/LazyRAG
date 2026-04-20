from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


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


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = strip_thinking(text)
    stripped = text
    if stripped.startswith('```'):
        stripped = stripped.split('\n', 1)[-1]
    if stripped.endswith('```'):
        stripped = stripped.rsplit('```', 1)[0]
    stripped = stripped.strip()

    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    for m in re.finditer(r'\{', stripped):
        start = m.start()
        depth, i = 0, start
        while i < len(stripped):
            ch = stripped[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(stripped[start: i + 1])
                        if isinstance(candidate, dict):
                            return candidate
                    except json.JSONDecodeError:
                        break
            i += 1
    return None


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
