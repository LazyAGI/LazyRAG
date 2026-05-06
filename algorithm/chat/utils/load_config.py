import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_CHAT_DIR = Path(__file__).resolve().parents[1]
_INNER_CONFIG_PATH = _CHAT_DIR / 'runtime_models.inner.yaml'
_EXTERNAL_CONFIG_PATH = _CHAT_DIR / 'runtime_models.yaml'
_ENV_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')

# Maps runtime_models.yaml type values to _dynamic_module_slot names used by
# _DynamicSourceRouterMixin subclasses (OnlineChatModule / OnlineEmbeddingModule).
_TYPE_TO_SLOT: Dict[str, str] = {
    'llm': 'chat',
    'chat': 'chat',
    'vlm': 'chat',
    'embed': 'embed',
    'rerank': 'embed',
    'cross_modal_embed': 'embed',
}


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
        config_path = lazyllm.config['auto_model_config_map_path'] or str(_EXTERNAL_CONFIG_PATH)
    path = Path(config_path)
    with path.open(encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}
    return _expand_env_placeholders(raw)


@lru_cache(maxsize=1)
def get_dynamic_role_slot_map(config_path: Optional[str] = None) -> Dict[str, str]:
    '''Return a mapping of {role_name: slot} for all roles with source=dynamic.

    slot is the _dynamic_module_slot value used by the corresponding online module
    class ('chat' for OnlineChatModule, 'embed' for OnlineEmbeddingModule).

    Example result for the default runtime_models.yaml:
        {
            'llm':        'chat',
            'llm_instruct': 'chat',
            'reranker':   'embed',
            'embed_main': 'embed',
        }
    '''
    raw = load_model_config(config_path)
    result: Dict[str, str] = {}
    for role, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        if (cfg.get('source') or '').lower() != 'dynamic':
            continue
        role_type = (cfg.get('type') or 'llm').lower()
        slot = _TYPE_TO_SLOT.get(role_type, 'chat')
        result[role] = slot
    return result


def coerce_bool(value: Any) -> Optional[bool]:
    '''Normalize a value to bool, handling string representations from HTTP JSON.

    JSON booleans deserialize correctly (true -> True), but if the client sends
    a string (e.g. "true", "false", "1", "0") we handle that too.
    Returns None when value is None so callers can distinguish "not provided".
    '''
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in ('false', '0', 'no', '')
    return bool(value)


def _make_bucket(cfg: Dict[str, Any]) -> Dict[str, Any]:
    '''Extract the fields that _DynamicSourceRouterMixin understands from a config dict.'''
    return {k: v for k, v in {
        'source': cfg.get('source'),
        'model': cfg.get('model'),
        'url': cfg.get('base_url'),
        'api_key': cfg.get('api_key'),
        'skip_auth': coerce_bool(cfg.get('skip_auth')),
    }.items() if v is not None}


def inject_model_config(model_config: Optional[Dict[str, Any]]) -> None:
    '''Inject per-request model configuration into lazyllm globals.

    model_config keys are role names defined in runtime_models.yaml (only roles
    with source=dynamic are relevant).  Each value is a config dict for that role:
        {
            "llm":        {"source": "openai", "model": "gpt-4o", "api_key": "sk-..."},
            "llm_instruct": {"source": "openai", "model": "gpt-4o-mini", "api_key": "sk-..."},
            "embed_main": {"source": "siliconflow", "model": "BAAI/bge-m3", "api_key": "..."},
            "reranker":   {"source": "siliconflow", "model": "BAAI/bge-reranker-v2-m3", "api_key": "..."},
        }

    ConfigsDict lookup chain (per _GlobalConfig.__getitem__):
        cfg[module.identities]  ->  [config_id, name, group_id, 'default']

    process_online_args sets name=<role_name> on each OnlineModule, so the
    lookup hits cfg[role_name] directly.  Each entry is {slot: bucket}, where
    slot is 'chat' (OnlineChatModule) or 'embed' (OnlineEmbeddingModule).

    This means two roles sharing the same slot (e.g. llm and llm_instruct) can
    carry independent configs as long as they have different role names.

    Raises ValueError if any dynamic role defined in runtime_models.yaml is
    missing from model_config — there is no fallback for dynamic sources.
    '''
    import lazyllm
    from lazyllm import LOG
    from lazyllm.module.llms.onlinemodule.dynamic_router import ConfigsDict

    role_slot_map = get_dynamic_role_slot_map()

    if not role_slot_map:
        return

    if not model_config:
        raise ValueError(
            f'model_config is required when dynamic roles are configured: '
            f'{sorted(role_slot_map)}'
        )

    missing = sorted(role for role in role_slot_map if role not in model_config)
    if missing:
        raise ValueError(
            f'model_config is missing required dynamic roles: {missing}. '
            f'All dynamic roles must be provided: {sorted(role_slot_map)}'
        )

    cfg = lazyllm.globals['config'].get('dynamic_model_configs') or ConfigsDict()
    if not isinstance(cfg, ConfigsDict):
        cfg = ConfigsDict(cfg)

    for role, role_cfg in model_config.items():
        if role not in role_slot_map:
            LOG.warning(f'[ChatServer] [MODEL_CONFIG] Unknown role {role!r}, skipping')
            continue
        if not isinstance(role_cfg, dict):
            raise ValueError(
                f'model_config[{role!r}] must be a dict, got {type(role_cfg).__name__!r}'
            )
        bucket = _make_bucket(role_cfg)
        if not bucket:
            raise ValueError(
                f'model_config[{role!r}] has no usable fields '
                f'(expected at least one of: source, model, base_url, api_key, skip_auth)'
            )
        slot = role_slot_map[role]
        role_dict = cfg.setdefault(role, {})
        role_dict[slot] = bucket
        # Hoist api_key to the role dict top level so _default_api_key() can read it
        # without knowing the slot type ('chat' vs 'embed').
        if (key := bucket.get('api_key')):
            role_dict['api_key'] = key

    lazyllm.globals['config']['dynamic_model_configs'] = cfg
