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


def rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    out = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1
        for k in range(i, j):
            out[indexed[k][0]] = avg
        i = j
    return out


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2:
        return None
    return pearson(rank(x), rank(y))


def kendall(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2:
        return None
    concordant = discordant = ties_x = ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = x[i] - x[j], y[i] - y[j]
            if dx == 0 and dy == 0:
                ties_x += 1
                ties_y += 1
            elif dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif (dx > 0 and dy > 0) or (dx < 0 and dy < 0):
                concordant += 1
            else:
                discordant += 1
    pairs = n * (n - 1) / 2
    denom = math.sqrt((pairs - ties_x) * (pairs - ties_y))
    if denom == 0:
        return None
    return (concordant - discordant) / denom


def partial_correlation(
    x: list[float], y: list[float], controls: list[list[float]],
) -> float | None:
    n = len(x)
    if n < 3 or not controls:
        return pearson(x, y)

    def _residuals(target: list[float]) -> list[float]:
        k = len(controls)
        xt = [[1.0] + [controls[c][i] for c in range(k)] for i in range(n)]
        xTx = [[sum(xt[r][a] * xt[r][b] for r in range(n)) for b in range(k + 1)]
               for a in range(k + 1)]
        xTy = [sum(xt[r][a] * target[r] for r in range(n)) for a in range(k + 1)]
        m = k + 1
        aug = [row[:] + [xTy[i]] for i, row in enumerate(xTx)]
        for col in range(m):
            pivot = max(range(col, m), key=lambda r: abs(aug[r][col]))
            aug[col], aug[pivot] = aug[pivot], aug[col]
            if abs(aug[col][col]) < 1e-12:
                return target
            for row in range(col + 1, m):
                f = aug[row][col] / aug[col][col]
                for j in range(col, m + 1):
                    aug[row][j] -= f * aug[col][j]
        beta = [0.0] * m
        for i in range(m - 1, -1, -1):
            beta[i] = aug[i][m]
            for j in range(i + 1, m):
                beta[i] -= aug[i][j] * beta[j]
            beta[i] /= aug[i][i]
        return [target[r] - sum(xt[r][a] * beta[a] for a in range(m)) for r in range(n)]

    return pearson(_residuals(x), _residuals(y))
