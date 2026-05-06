import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

_CHAT_DIR = Path(__file__).resolve().parents[1]
_INNER_CONFIG_PATH = _CHAT_DIR / 'runtime_models.inner.yaml'
_EXTERNAL_CONFIG_PATH = _CHAT_DIR / 'runtime_models.yaml'
_ENV_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')


def _expand_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            env_val = os.environ.get(m.group(1))
            if env_val is not None:
                return env_val
            default = m.group(2)
            return default if default is not None else m.group(0)
        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _expand_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_placeholders(item) for item in value]
    return value


def load_model_config(config_path: str | None = None) -> Dict[str, Any]:
    '''Load and return the model config dict with environment variables expanded.

    When config_path is None, falls back to the path set by
    LAZYLLM_AUTO_MODEL_CONFIG_MAP_PATH (same env var AutoModel uses with config=True).
    '''
    if config_path is None:
        import lazyllm
        config_path = lazyllm.config.get('auto_model_config_map_path') or str(_EXTERNAL_CONFIG_PATH)
    path = Path(config_path)
    with path.open(encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}
    return _expand_env_placeholders(raw)
