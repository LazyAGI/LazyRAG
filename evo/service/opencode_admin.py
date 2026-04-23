from __future__ import annotations

import json
import os
import time
from pathlib import Path

from evo.apply import opencode as oc
from evo.apply.errors import ApplyError
from evo.runtime.config import EvoConfig


def auth_path(config: EvoConfig) -> Path:
    return config.storage.opencode_dir / 'auth.json'


def _load(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def read_status(config: EvoConfig) -> dict:
    p = auth_path(config)
    data = _load(p)
    return {
        'authenticated': bool(data),
        'path': str(p),
        'providers': sorted(data.keys()),
        'last_check_at': time.time(),
    }


def write_config(config: EvoConfig, *, provider: str, api_key: str,
                 model: str | None = None) -> dict:
    if not provider or not api_key:
        raise ApplyError('OPENCODE_AUTH_MISSING',
                         'provider and api_key are required',
                         {'provider': provider})
    p = auth_path(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _load(p)
    entry: dict = {'type': 'api', 'key': api_key}
    if model:
        entry['model'] = model
    data[provider] = entry
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)
    oc.preflight(None, auth_dir=config.storage.opencode_dir)
    return read_status(config)


def clear_config(config: EvoConfig) -> dict:
    p = auth_path(config)
    if p.exists():
        p.unlink()
    return read_status(config)
