import functools
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

_CHAT_DIR = Path(__file__).resolve().parents[1]
_INNER_CONFIG_PATH = _CHAT_DIR / 'runtime_models.inner.yaml'
_EXTERNAL_CONFIG_PATH = _CHAT_DIR / 'runtime_models.yaml'
_ENV_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')

_NON_MODEL_KEYS = frozenset({'embeddings', 'retrieval', 'roles'})

_DEFAULT_INDEX_KWARGS: Dict[str, Any] = {
    'index_type': 'IVF_FLAT',
    'metric_type': 'COSINE',
    'params': {'nlist': 128},
}


@dataclass(frozen=True)
class RetrievalSettings:
    embed_keys: List[str]
    index_kwargs: List[Dict[str, Any]]
    retriever_configs: List[Dict[str, Any]]
    temp_doc_embed_key: str
    file_search_embed_key: str


def _expand_env_placeholders(value: Any, config_path: str) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env_placeholders(v, config_path) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_placeholders(item, config_path) for item in value]
    if not isinstance(value, str):
        return value

    def _replace(match: re.Match) -> str:
        env_name = match.group(1)
        default = match.group(2)
        resolved = os.getenv(env_name)
        if resolved is not None:
            return resolved
        if default is not None:
            return default
        raise ValueError(
            f'Environment variable `{env_name}` is required by model config `{config_path}`'
        )

    expanded = _ENV_PATTERN.sub(_replace, value)
    if isinstance(expanded, str):
        expanded = expanded.strip()
        return expanded or None
    return expanded


def get_config_path() -> Path:
    custom = os.getenv('LAZYRAG_MODEL_CONFIG_PATH')
    if custom:
        return Path(custom)
    use_inner_raw = os.getenv('LAZYRAG_USE_INNER_MODEL')
    # Default to inner runtime config unless explicitly disabled.
    if use_inner_raw is None:
        use_inner = True
    else:
        use_inner = use_inner_raw.lower() in ('1', 'true', 'yes')
    return _INNER_CONFIG_PATH if use_inner else _EXTERNAL_CONFIG_PATH


def load_model_config(config_path: str | None = None) -> Dict[str, Any]:
    resolved = Path(config_path) if config_path else get_config_path()
    if not resolved.exists():
        raise FileNotFoundError(
            f'Model config `{resolved}` not found. '
            'Set LAZYRAG_MODEL_CONFIG_PATH, or set LAZYRAG_USE_INNER_MODEL=false to use runtime_models.yaml.'
        )
    with resolved.open('r', encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f'Model config `{resolved}` root must be a mapping.')
    return _expand_env_placeholders(raw, str(resolved))


_config_cache: Dict[str, Any] | None = None


def _get_cached_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is None:
        _config_cache = load_model_config()
    return _config_cache


def _get_roles(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get('roles', cfg)


def get_role_config(role: str) -> Tuple[str, Dict[str, Any]]:
    cfg = _get_cached_config()
    roles = _get_roles(cfg)

    if role in roles and role not in _NON_MODEL_KEYS:
        entry = roles[role]
    elif isinstance(roles.get('embeddings'), dict) and role in roles['embeddings']:
        entry = roles['embeddings'][role]
    else:
        available = [k for k in roles if k not in _NON_MODEL_KEYS]
        embed_keys = list(roles.get('embeddings', {}).keys())
        raise KeyError(
            f'Unknown model role {role!r}. '
            f'Available roles: {available}, embed keys: {embed_keys}'
        )

    if not isinstance(entry, dict):
        raise ValueError(f'Model role `{role}` config must be a mapping.')

    config = deepcopy(entry)
    model_name = config.pop('model', None) or config.pop('name', None)
    if not model_name:
        raise ValueError(f'Model role `{role}` missing `model` field.')
    config.pop('index_kwargs', None)
    config.pop('name', None)
    return model_name, config


def _build_default_retriever_configs(embed_keys: List[str], topk: int = 20) -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    for ek in embed_keys:
        configs.append({'group_name': 'line', 'embed_keys': [ek], 'topk': topk, 'target': 'block'})
    for ek in embed_keys:
        configs.append({'group_name': 'block', 'embed_keys': [ek], 'topk': topk})
    return configs


def _default_file_search_embed_key(embed_keys: List[str], index_kwargs: List[Dict[str, Any]]) -> str:
    for ik in index_kwargs:
        if 'SPARSE' in str(ik.get('index_type', '')).upper():
            return ik['embed_key']
    return embed_keys[0]


@functools.lru_cache(maxsize=1)
def get_retrieval_settings(config_path: str | None = None) -> RetrievalSettings:
    cfg = load_model_config(config_path)
    roles = _get_roles(cfg)
    embeddings = roles.get('embeddings', {})

    embed_keys: List[str] = []
    index_kwargs: List[Dict[str, Any]] = []
    for key, entry in embeddings.items():
        if not entry or not isinstance(entry, dict):
            continue
        embed_keys.append(key)
        ik = deepcopy(entry.get('index_kwargs')) if isinstance(entry.get('index_kwargs'), dict) \
            else deepcopy(_DEFAULT_INDEX_KWARGS)
        ik['embed_key'] = key
        index_kwargs.append(ik)

    if not embed_keys:
        raise ValueError(
            'At least one embedding must be configured under `embeddings`.'
        )

    retrieval = cfg.get('retrieval', roles.get('retrieval', {})) or {}

    temp_doc_embed_key = retrieval.get('temp_doc_embed_key', embed_keys[0])
    if temp_doc_embed_key not in embed_keys:
        raise ValueError(
            f'temp_doc_embed_key `{temp_doc_embed_key}` not in active embeds: {embed_keys}'
        )

    file_search_embed_key = retrieval.get(
        'file_search_embed_key',
        _default_file_search_embed_key(embed_keys, index_kwargs),
    )
    if file_search_embed_key not in embed_keys:
        raise ValueError(
            f'file_search_embed_key `{file_search_embed_key}` not in active embeds: {embed_keys}'
        )

    retriever_configs = retrieval.get('retriever_configs')
    if retriever_configs is None:
        topk = int(retrieval.get('default_topk', 20))
        retriever_configs = _build_default_retriever_configs(embed_keys, topk)

    return RetrievalSettings(
        embed_keys=embed_keys,
        index_kwargs=index_kwargs,
        retriever_configs=retriever_configs,
        temp_doc_embed_key=temp_doc_embed_key,
        file_search_embed_key=file_search_embed_key,
    )
