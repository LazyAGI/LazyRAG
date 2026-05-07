from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import lazyllm
import yaml

_CHAT_DIR = Path(__file__).resolve().parents[1]
_INNER_CONFIG_PATH = _CHAT_DIR / 'runtime_models.inner.yaml'
_ONLINE_CONFIG_PATH = _CHAT_DIR / 'runtime_models.online.yaml'
_DYNAMIC_CONFIG_PATH = _CHAT_DIR / 'runtime_models.yaml'

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

# Prefix convention for embed-type roles in the flat yaml format.
# Any top-level key starting with this prefix is treated as an embed role.
_EMBED_KEY_PREFIX = 'embed_'


def get_config_path() -> str:
    '''Return the active runtime_models config file path as a string.

    Controlled entirely by LAZYRAG_MODEL_CONFIG_PATH.  Three shorthand values
    are accepted in addition to an explicit file path:

        inner    → runtime_models.inner.yaml   (intranet / on-prem deployment)
        online   → runtime_models.online.yaml  (public cloud API deployment)
        dynamic  → runtime_models.yaml         (fully dynamic, key injected per request)

    If the env var is not set, defaults to 'dynamic'.
    '''
    # Aliases are resolved at call time (not at import time) so that tests can
    # patch the module-level path variables and have the change take effect.
    aliases = {
        'inner': _INNER_CONFIG_PATH,
        'online': _ONLINE_CONFIG_PATH,
        'dynamic': _DYNAMIC_CONFIG_PATH,
    }
    from config import config as _cfg
    raw = _cfg['model_config_path']
    if raw in aliases:
        return str(aliases[raw])
    return raw


def load_model_config(config_path: str | None = None) -> Dict[str, Any]:
    '''Load and return the raw model config dict (yaml parsed, no env expansion).

    When config_path is None, falls back to the path resolved by get_config_path()
    (controlled by LAZYRAG_MODEL_CONFIG_PATH).
    '''
    with Path(config_path or get_config_path()).open(encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


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

    When config_path is None, reads from _DYNAMIC_CONFIG_PATH (runtime_models.yaml).
    This is intentionally independent of LAZYRAG_MODEL_CONFIG_PATH: the dynamic role
    map describes which roles expect per-request key injection, and that is always
    defined in the dynamic config file regardless of which config is active at runtime.
    '''
    raw = load_model_config(config_path or str(_DYNAMIC_CONFIG_PATH))
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
    if value is None: return None
    if isinstance(value, int): return bool(value)  # bool is subclass of int
    if isinstance(value, str): return value.strip().lower() not in ('false', '0', 'no', '')
    return bool(value)


def _make_bucket(cfg: Dict[str, Any]) -> Dict[str, Any]:
    '''Extract the fields that _DynamicSourceRouterMixin understands from a config dict.

    Note: api_key is intentionally excluded here.  It is stored separately in
    globals.config['{source}_api_key'] (a ConfigsDict keyed by role name) so
    that _default_api_key() can retrieve it dynamically via the stack lookup
    mechanism in _GlobalConfig.__getitem__.  See inject_model_config for details.
    '''
    return {k: v for k, v in {'source': cfg.get('source'), 'model': cfg.get('model'), 'url': cfg.get('base_url'),
                              'skip_auth': coerce_bool(cfg.get('skip_auth'))}.items() if v is not None}


def inject_model_config(model_config: Optional[Dict[str, Any]]) -> None:
    '''Inject per-request model configuration into lazyllm globals.

    model_config keys are role names defined in runtime_models.yaml (only roles
    with source=dynamic are relevant).  Each value is a config dict for that role:
        {
            "llm":        {"source": "openai",      "model": "gpt-4o",      "api_key": "sk-..."},
            "llm_instruct": {"source": "openai",    "model": "gpt-4o-mini", "api_key": "sk-..."},
            "embed_main": {"source": "siliconflow", "model": "BAAI/bge-m3", "api_key": "..."},
            "reranker":   {"source": "siliconflow", "model": "BAAI/bge-reranker-v2-m3", "api_key": "..."},
        }

    After this call, globals has the following structure:

        globals['config']['dynamic_model_configs'] = ConfigsDict({
            'llm':          {'chat':  {'source': 'openai',      'model': 'gpt-4o',      ...}},
            'llm_instruct': {'chat':  {'source': 'openai',      'model': 'gpt-4o-mini', ...}},
            'embed_main':   {'embed': {'source': 'siliconflow', 'model': 'bge-m3',       ...}},
            'reranker':     {'embed': {'source': 'siliconflow', 'model': 'bge-reranker', ...}},
        })
        # api_key is NOT stored in dynamic_model_configs.  It lives in the
        # per-source config key so that _GlobalConfig.__getitem__ can resolve it
        # dynamically via the stack lookup (stack = [config_id, role_name, group_id]):
        globals['config']['openai_api_key'] = ConfigsDict({
            'llm':          'sk-...',
            'llm_instruct': 'sk-...',
        })
        globals['config']['siliconflow_api_key'] = ConfigsDict({
            'embed_main': 'sk-...',
            'reranker':   'sk-...',
        })

    Lookup chain at forward() time (OnlineChatModule with name='llm'):
        stack_enter(m.identities)           # stack = [config_id, 'llm', group_id]
        _build_supplier('openai', False)
          → OpenAIChat(api_key='dynamic')   # _dynamic_auth = True
        supplier.forward()
          → _api_key → _materialize_lazy_api_key()
              → _default_api_key()
                  → globals.config['openai_api_key']
                      → ConfigsDict lookup hits cfg['llm'] = 'sk-...'  ✓

    Two roles with the same source but different keys (e.g. llm / llm_instruct)
    are fully isolated because the ConfigsDict is keyed by role name, and each
    module's stack contains its own role name.

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

    # Build the new dynamic_model_configs ConfigsDict (source/model/url/skip_auth only).
    # We read the existing value directly from the underlying globals['config'] dict
    # (not via globals.config[...]) because the latter requires a non-empty stack and
    # is intended for per-forward reads, not for the write path here.
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
                f'(expected at least one of: source, model, base_url, skip_auth)'
            )
        slot = role_slot_map[role]
        cfg.setdefault(role, {})[slot] = bucket

        # Store api_key in globals.config['{source}_api_key'] as a ConfigsDict
        # keyed by role name.  _default_api_key() reads this via the stack-based
        # lookup in _GlobalConfig.__getitem__, so each role gets its own key even
        # when multiple roles share the same source.
        #
        # We write to globals['config'] directly (bypassing _GlobalConfig.__setitem__)
        # because {source}_api_key may not yet be in _supported_configs at call time
        # (it is added lazily when the supplier class is first registered).
        if (api_key := role_cfg.get('api_key')) and (source := role_cfg.get('source')):
            config_key = f'{source}_api_key'
            existing = lazyllm.globals['config'].get(config_key)
            if not isinstance(existing, ConfigsDict):
                existing = ConfigsDict({'default': existing} if existing else {})
            existing[role] = api_key
            lazyllm.globals['config'][config_key] = existing

    lazyllm.globals['config']['dynamic_model_configs'] = cfg


@lru_cache(maxsize=1)
def get_embed_keys(config_path: Optional[str] = None) -> list:
    '''Return the list of embed-type role names defined in the active config.

    A role is considered an embed role when its key starts with the prefix
    ``embed_`` (e.g. ``embed_main``, ``embed_sparse``).  The order matches the
    yaml definition order, so the first key is always the primary (dense) embed.

    Returns an empty list when no embed roles are found (caller should handle
    this as a configuration error).
    '''
    raw = load_model_config(config_path)
    return [role for role in raw if role.startswith(_EMBED_KEY_PREFIX)]


_DEFAULT_DENSE_INDEX_KWARGS = {
    'index_type': 'IVF_FLAT',
    'metric_type': 'COSINE',
    'params': {'nlist': 128},
}

_DEFAULT_SPARSE_INDEX_KWARGS = {
    'index_type': 'SPARSE_INVERTED_INDEX',
    'metric_type': 'IP',
}


@lru_cache(maxsize=1)
def get_embed_index_kwargs(config_path: Optional[str] = None) -> list:
    '''Return a list of index_kwargs dicts (one per embed role) for the vector store.

    Each dict contains an `embed_key` field plus the Milvus index parameters.
    The index params are read from the yaml entry's `index_kwargs` field when
    present; otherwise a default is inferred from the model name:
      - names containing "sparse" → SPARSE_INVERTED_INDEX / IP
      - everything else           → IVF_FLAT / COSINE
    '''
    from copy import deepcopy
    raw = load_model_config(config_path)
    result = []
    for role, entries in raw.items():
        if not role.startswith(_EMBED_KEY_PREFIX):
            continue
        if not isinstance(entries, list) or not entries:
            continue
        entry = entries[0]
        if 'index_kwargs' in entry:
            ik = deepcopy(entry['index_kwargs'])
        else:
            model_name = (entry.get('name') or entry.get('model') or '').lower()
            ik = deepcopy(_DEFAULT_SPARSE_INDEX_KWARGS if 'sparse' in model_name
                          else _DEFAULT_DENSE_INDEX_KWARGS)
        ik['embed_key'] = role
        result.append(ik)
    return result
