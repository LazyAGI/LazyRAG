from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from lazyllm.tools.agent.skill_manager import SkillManager as LazySkillManager

_COMMON_DIR = Path(__file__).resolve().parents[2] / 'common'
_INNER_CONFIG_PATH = _COMMON_DIR / 'runtime_models.inner.yaml'
_ONLINE_CONFIG_PATH = _COMMON_DIR / 'runtime_models.online.yaml'
_DYNAMIC_CONFIG_PATH = _COMMON_DIR / 'runtime_models.yaml'

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
_EMBED_TYPES = {'embed', 'cross_modal_embed'}
_IMAGE_EMBED_TYPES = {'cross_modal_embed'}


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
        path = str(aliases[raw])
    else:
        path = raw
    return path


def load_model_config(config_path: str | None = None) -> Dict[str, Any]:
    '''Load and return the raw model config dict (yaml parsed, no env expansion).

    When config_path is None, falls back to the path resolved by get_config_path()
    (controlled by LAZYRAG_MODEL_CONFIG_PATH).
    '''
    with Path(config_path or get_config_path()).open(encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def normalize_skill_fs_url(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    parts = [part.strip() for part in raw.split(',') if part.strip()]
    if not parts:
        return ''
    if parts[0].startswith('remote://') and '.agentic/skills' not in parts:
        parts.append('.agentic/skills')
    return ','.join(parts)


def extract_skill_fs_source(path: Any) -> str:
    raw = str(path or '').strip()
    if not raw:
        return 'file'
    protocol = LazySkillManager._extract_protocol(raw)
    if protocol == 'remote':
        return 'remote'
    return protocol or 'file'


@lru_cache(maxsize=1)
def get_dynamic_role_slot_map(config_path: Optional[str] = None) -> Dict[str, str]:
    '''Return a mapping of {role_name: slot} for all roles with source=dynamic.

    slot is the _dynamic_module_slot value used by the corresponding online module
    class ('chat' for OnlineChatModule, 'embed' for OnlineEmbeddingModule).

    Example result for the default runtime_models.yaml:
        {
            'llm':        'chat',
            'reranker':   'embed',
            'embed_main': 'embed',
        }

    When config_path is None, reads from _DYNAMIC_CONFIG_PATH (runtime_models.yaml).
    Pass get_config_path() to read from the currently active config file instead.
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


def _api_key_state(value: Any) -> str:
    return 'set' if value else 'empty'


def summarize_model_config_for_log(model_config: Optional[Dict[str, Any]]) -> str:
    '''Return a deterministic, API-key-safe summary for model_config logs.'''
    if not model_config:
        return 'roles=[]'

    parts = []
    for role in sorted(str(k) for k in model_config.keys()):
        role_cfg = model_config.get(role)
        if not isinstance(role_cfg, dict):
            parts.append(f'{role}(type={type(role_cfg).__name__})')
            continue
        fields = [
            f'source={role_cfg.get("source", "")}',
            f'model={role_cfg.get("model", "")}',
            f'base_url={role_cfg.get("base_url", "")}',
            f'api_key={_api_key_state(role_cfg.get("api_key"))}',
        ]
        if 'skip_auth' in role_cfg:
            fields.append(f'skip_auth={coerce_bool(role_cfg.get("skip_auth"))}')
        parts.append(f'{role}(' + ', '.join(fields) + ')')
    return f'roles={sorted(str(k) for k in model_config.keys())} ' + '; '.join(parts)


def inject_model_config(model_config: Optional[Dict[str, Any]]) -> None:
    '''Inject per-request model configuration into lazyllm globals.

    model_config keys are role names defined in runtime_models.yaml (only roles
    with source=dynamic are relevant).  Each value is a config dict for that role:
        {
            "llm":        {"source": "openai",      "model": "gpt-4o",      "api_key": "sk-..."},
            "embed_main": {"source": "siliconflow", "model": "BAAI/bge-m3", "api_key": "..."},
            "reranker":   {"source": "siliconflow", "model": "BAAI/bge-reranker-v2-m3", "api_key": "..."},
        }

    After this call, globals has the following structure:

        globals.config['dynamic_model_configs'] = ConfigsDict({
            'llm':          {'chat':  {'source': 'openai',      'model': 'gpt-4o',      ...}},
            'embed_main':   {'embed': {'source': 'siliconflow', 'model': 'bge-m3',       ...}},
            'reranker':     {'embed': {'source': 'siliconflow', 'model': 'bge-reranker', ...}},
        })
        # api_key is NOT stored in dynamic_model_configs.  It lives in the
        # per-source config key so that _GlobalConfig.__getitem__ can resolve it
        # dynamically via the stack lookup (stack = [config_id, role_name, group_id]):
        globals.config['openai_api_key'] = ConfigsDict({
            'llm':          'sk-...',
        })
        globals.config['siliconflow_api_key'] = ConfigsDict({
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

    Two roles with the same source but different keys (e.g. llm / evo_llm)
    are fully isolated because the ConfigsDict is keyed by role name, and each
    module's stack contains its own role name.

    Missing dynamic roles are logged and left unconfigured.  If a later pipeline
    uses one of those roles, LazyLLM will fail with a role-specific "No source"
    error instead of silently falling back to a static provider.
    '''
    import lazyllm
    from lazyllm import LOG
    from lazyllm.module.llms.onlinemodule.dynamic_router import ConfigsDict

    # Pass the active config path so get_dynamic_role_slot_map reads the correct
    # file (e.g. runtime_models.online.yaml) instead of always falling back to
    # _DYNAMIC_CONFIG_PATH (runtime_models.yaml), which has no dynamic roles when
    # LAZYRAG_MODEL_CONFIG_PATH=online/inner.
    config_path = get_config_path()
    role_slot_map = get_dynamic_role_slot_map(config_path)

    if not role_slot_map:
        if model_config:
            LOG.warning(
                f'[ChatServer] [MODEL_CONFIG_SKIPPED] [reason=no_dynamic_roles] '
                f'[active_config={config_path}] [{summarize_model_config_for_log(model_config)}]'
            )
        return

    if not model_config:
        LOG.error(
            f'[ChatServer] [MODEL_CONFIG_MISSING] [active_config={config_path}] '
            f'[dynamic_roles={sorted(role_slot_map)}]'
        )
        raise ValueError(
            f'model_config is required when dynamic roles are configured: '
            f'{sorted(role_slot_map)}'
        )

    missing = sorted(role for role in role_slot_map if role not in model_config)
    if missing:
        LOG.warning(
            f'[ChatServer] [MODEL_CONFIG_PARTIAL] [active_config={config_path}] '
            f'[missing_roles={missing}] [dynamic_roles={sorted(role_slot_map)}] '
            f'[{summarize_model_config_for_log(model_config)}]'
        )

    # Build the per-request dynamic_model_configs ConfigsDict (source/model/url/skip_auth only).
    # Use globals.config[...] for writes so LazyLLM's supported-config registry is respected.
    # We avoid reading existing ConfigsDict via globals.config[...] here because stack-based
    # lookup is for per-forward reads; this request supplies the full dynamic role set.
    cfg = ConfigsDict()
    api_key_configs: Dict[str, Any] = {}
    injected_roles = []

    for role, role_cfg in model_config.items():
        if role not in role_slot_map:
            LOG.warning(f'[ChatServer] [MODEL_CONFIG_UNKNOWN_ROLE] [role={role!r}] [active_config={config_path}]')
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
        injected_roles.append(role)

        # Store api_key in globals.config['{source}_api_key'] as a ConfigsDict
        # keyed by role name.  _default_api_key() reads this via the stack-based
        # lookup in _GlobalConfig.__getitem__, so each role gets its own key even
        # when multiple roles share the same source.
        #
        if (api_key := role_cfg.get('api_key')) and (source := role_cfg.get('source')):
            config_key = f'{source}_api_key'
            api_key_configs.setdefault(config_key, ConfigsDict())[role] = api_key

    for config_key, api_key_cfg in api_key_configs.items():
        lazyllm.globals.config[config_key] = api_key_cfg
    lazyllm.globals.config['dynamic_model_configs'] = cfg
    LOG.info(
        f'[ChatServer] [MODEL_CONFIG_INJECTED] [active_config={config_path}] '
        f'[dynamic_roles={sorted(role_slot_map)}] [injected_roles={sorted(injected_roles)}] '
        f'[{summarize_model_config_for_log(model_config)}]'
    )


@lru_cache(maxsize=1)
def get_embed_keys(config_path: Optional[str] = None) -> list:
    '''Return the list of embed-type role names defined in the active config.

    A role is considered an embed role when its first-entry ``type`` is one of
    ``embed`` / ``rerank`` / ``cross_modal_embed``. For backward compatibility,
    keys that start with ``embed_`` are also treated as embed roles.
    The order matches the yaml definition order, so the first key is always the
    primary (dense) embed.

    Returns an empty list when no embed roles are found (caller should handle
    this as a configuration error).
    '''
    raw = load_model_config(config_path)
    return [role for role, entries in raw.items() if _is_embed_role(role, entries)]


def _first_entry_type(entries: Any) -> str:
    '''Return the lower-cased ``type`` field from the first entry.

    Supports both yaml shapes:
      - static (inner/online): ``role: [{type: ...}, ...]``
      - dynamic              : ``role: {type: ...}``
    '''
    if isinstance(entries, list) and entries:
        entry = entries[0]
    elif isinstance(entries, dict):
        entry = entries
    else:
        return ''
    if not isinstance(entry, dict):
        return ''
    return (entry.get('type') or '').lower()


def _is_embed_role(role: str, entries: Any) -> bool:
    '''Return whether the role should be treated as an embed role.'''
    entry_type = _first_entry_type(entries)
    if entry_type in _EMBED_TYPES:
        return True
    return role.startswith(_EMBED_KEY_PREFIX)


@lru_cache(maxsize=1)
def get_image_embed_key(config_path: Optional[str] = None) -> Optional[str]:
    '''Return the embed role name identified as the image embed.

    A role is treated as the image embed when its first entry has
    ``type: cross_modal_embed``. For backward compatibility, it also falls
    back to ``name: siglip`` (case-insensitive) when type is not provided.
    Returns None when no such role exists, in which case callers should skip
    the image retrieval branch.
    '''
    raw = load_model_config(config_path)
    for role, entries in raw.items():
        if not _is_embed_role(role, entries):
            continue
        if isinstance(entries, list) and entries:
            entry = entries[0]
        elif isinstance(entries, dict):
            entry = entries
        else:
            continue
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get('type') or '').strip().lower()
        if entry_type in _IMAGE_EMBED_TYPES:
            return role
        model_name = str(entry.get('name') or '').strip().lower()
        if model_name == 'siglip':
            return role
    return None


@lru_cache(maxsize=1)
def get_text_embed_keys(config_path: Optional[str] = None) -> list:
    '''Return embed role names excluding the cross-modal image embed.'''
    image_key = get_image_embed_key(config_path)
    return [k for k in get_embed_keys(config_path) if k != image_key]


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
        if not _is_embed_role(role, entries):
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
