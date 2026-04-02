import functools
import hashlib
import os
import re
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import lazyllm
import yaml
from lazyllm import AutoModel

DEFAULT_AUTO_MODEL_CONFIG_PATH = Path(__file__).resolve().parents[2] / 'configs' / 'auto_model.yaml'
DEFAULT_RUNTIME_MODEL_CONFIG_PATH = Path(__file__).resolve().parents[2] / 'configs' / 'runtime_models.yaml'
DEFAULT_EMBED_KEYS = ('embed_1', 'embed_2', 'embed_3')
LEGACY_DENSE_EMBED_KEY = 'bge_m3_dense'
LEGACY_SPARSE_EMBED_KEY = 'bge_m3_sparse'
LEGACY_LLM_MODEL = 'qwen3_32b_custom'
LEGACY_LLM_INSTRUCT_MODEL = 'qwen3_moe_custom'
LEGACY_RERANKER_MODEL = 'qwen3_reranker_custom'
LEGACY_DENSE_EMBED_MODEL = 'bgem3_emb_dense_custom'
LEGACY_SPARSE_EMBED_MODEL = 'bgem3_emb_sparse_custom'
DEFAULT_EMBED_INDEX_KWARGS = {
    'index_type': 'IVF_FLAT',
    'metric_type': 'COSINE',
    'params': {
        'nlist': 128,
    },
}
LEGACY_SPARSE_EMBED_INDEX_KWARGS = {
    'index_type': 'SPARSE_INVERTED_INDEX',
    'metric_type': 'IP',
    'params': {
        'nlist': 128,
    },
}
_ENV_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')


@dataclass(frozen=True)
class RuntimeModelSettings:
    llm: Any
    llm_instruct: Any
    reranker: Any
    embeddings: Dict[str, Any]
    embed_keys: List[str]
    index_kwargs: List[Dict[str, Any]]
    retriever_configs: List[Dict[str, Any]]
    temp_doc_embed_key: str
    file_search_embed_key: str


def get_runtime_model_config_path() -> str:
    return os.getenv('LAZYRAG_MODEL_CONFIG_PATH') or str(DEFAULT_RUNTIME_MODEL_CONFIG_PATH)


def has_explicit_runtime_model_config() -> bool:
    return bool(os.getenv('LAZYRAG_MODEL_CONFIG_PATH'))


def get_auto_model_config_path() -> str:
    config_path = os.getenv('CONFIG_PATH')
    if config_path:
        return config_path

    try:
        config_path = lazyllm.config['auto_model_config_map_path']
        if config_path:
            return config_path
        config_path = lazyllm.config['trainable_module_config_map_path']
        if config_path:
            return config_path
    except Exception:
        pass

    return (
        os.getenv('AUTO_MODEL_CONFIG_MAP_PATH')
        or os.getenv('TRAINABLE_MODULE_CONFIG_MAP_PATH')
        or str(DEFAULT_AUTO_MODEL_CONFIG_PATH)
    )


def load_auto_model_config(config_path: str | None = None) -> Dict[str, Any]:
    resolved_path = Path(config_path or get_auto_model_config_path())
    with resolved_path.open('r', encoding='utf-8') as file:
        return yaml.safe_load(file) or {}


@functools.lru_cache(maxsize=64)
def _write_runtime_auto_model_config(serialized_config: str) -> str:
    config = yaml.safe_load(serialized_config)
    model_name = config['model']
    digest = hashlib.sha256(serialized_config.encode('utf-8')).hexdigest()[:16]
    safe_model_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', model_name).strip('-') or 'runtime-model'
    target_dir = Path(tempfile.gettempdir()) / 'lazyrag-runtime-auto-model'
    target_dir.mkdir(parents=True, exist_ok=True)
    config_path = target_dir / f'{safe_model_name}-{digest}.yaml'
    with config_path.open('w', encoding='utf-8') as file:
        yaml.safe_dump({model_name: [config]}, file, sort_keys=False)
    return str(config_path)


def _strip_optional_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = value.strip()
    return value or None


def _expand_env_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_placeholders(item) for item in value]
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
            f'Environment variable `{env_name}` is required by model config '
            f'`{get_runtime_model_config_path()}`'
        )

    expanded = _ENV_PATTERN.sub(_replace, value)
    return _strip_optional_string(expanded)


def load_runtime_model_config(config_path: str | None = None) -> Dict[str, Any]:
    resolved_path = Path(config_path or get_runtime_model_config_path())
    if not resolved_path.exists():
        raise FileNotFoundError(
            f'Runtime model config `{resolved_path}` not found. '
            'Set `LAZYRAG_MODEL_CONFIG_PATH` or create the default config file.'
        )

    with resolved_path.open('r', encoding='utf-8') as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError(f'Runtime model config `{resolved_path}` must be a mapping.')
    return _expand_env_placeholders(raw)


def _get_runtime_roles(config: Dict[str, Any]) -> Dict[str, Any]:
    roles = config.get('roles', config)
    if not isinstance(roles, dict):
        raise ValueError('Runtime model config `roles` must be a mapping.')
    return roles


def _normalize_model_entry(name: str, entry: Dict[str, Any], expected_type: str) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f'Model role `{name}` must be a mapping.')

    normalized = deepcopy(entry)
    alias_model = _strip_optional_string(normalized.pop('name', None))
    model = _strip_optional_string(normalized.get('model'))
    if model and alias_model and model != alias_model:
        raise ValueError(f'Model role `{name}` cannot define both `model` and `name` with different values.')
    model = model or alias_model
    source = _strip_optional_string(normalized.get('source'))
    type_name = _strip_optional_string(normalized.get('type')) or expected_type
    api_key = _strip_optional_string(normalized.get('api_key'))
    url = _strip_optional_string(normalized.get('url'))

    if not source:
        raise ValueError(f'Model role `{name}` missing required field `source`.')
    if not model:
        raise ValueError(f'Model role `{name}` missing required field `model`.')
    if type_name != expected_type:
        raise ValueError(
            f'Model role `{name}` has type `{type_name}`, expected `{expected_type}`.'
        )
    if not api_key and not normalized.get('skip_auth'):
        raise ValueError(
            f'Model role `{name}` missing required field `api_key`. '
            'Use `${ENV_NAME}` in config or set `skip_auth: true` for unauthenticated endpoints.'
        )

    normalized['model'] = model
    normalized['source'] = source
    normalized['type'] = expected_type
    if url:
        normalized['url'] = url
    elif 'url' in normalized:
        normalized.pop('url')
    if api_key:
        normalized['api_key'] = api_key
    elif 'api_key' in normalized:
        normalized.pop('api_key')
    return normalized


def _normalize_index_kwargs(embed_key: str, index_kwargs: Any) -> Dict[str, Any]:
    if index_kwargs is None:
        normalized = deepcopy(DEFAULT_EMBED_INDEX_KWARGS)
    elif isinstance(index_kwargs, dict):
        normalized = deepcopy(index_kwargs)
    else:
        raise ValueError(f'Embedding `{embed_key}` field `index_kwargs` must be a mapping.')

    normalized['embed_key'] = embed_key
    return normalized


def _normalize_embed_configs(
    roles: Dict[str, Any]
) -> tuple[Dict[str, Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    embeddings = roles.get('embeddings')
    if embeddings is None:
        embeddings = {key: roles.get(key) for key in DEFAULT_EMBED_KEYS if roles.get(key) is not None}
    if not isinstance(embeddings, dict):
        raise ValueError('Runtime model config `embeddings` must be a mapping.')

    unsupported_keys = set(embeddings) - set(DEFAULT_EMBED_KEYS)
    if unsupported_keys:
        raise ValueError(
            f'Unsupported embedding slots: {sorted(unsupported_keys)!r}. '
            f'Only {list(DEFAULT_EMBED_KEYS)!r} are allowed.'
        )

    normalized_embeddings: Dict[str, Dict[str, Any]] = {}
    embed_keys: List[str] = []
    index_kwargs: List[Dict[str, Any]] = []
    for embed_key in DEFAULT_EMBED_KEYS:
        entry = embeddings.get(embed_key)
        if not entry:
            continue
        normalized = _normalize_model_entry(embed_key, entry, 'embed')
        index_kwargs.append(_normalize_index_kwargs(embed_key, normalized.pop('index_kwargs', None)))
        normalized_embeddings[embed_key] = normalized
        embed_keys.append(embed_key)

    if not embed_keys:
        raise ValueError(
            'Runtime model config must enable at least one embedding slot among '
            f'{list(DEFAULT_EMBED_KEYS)!r}.'
        )
    return normalized_embeddings, embed_keys, index_kwargs


def _resolve_embed_key(name: str, embed_key: str, allowed_keys: List[str]) -> str:
    if embed_key not in allowed_keys:
        raise ValueError(
            f'Config field `{name}` references unknown embed key `{embed_key}`. '
            f'Enabled keys: {allowed_keys!r}.'
        )
    return embed_key


def _default_file_search_embed_key(embed_keys: List[str], index_kwargs: List[Dict[str, Any]]) -> str:
    for item in index_kwargs:
        if 'SPARSE' in str(item.get('index_type', '')).upper():
            return item['embed_key']
    return embed_keys[0]


def _build_default_retriever_configs(embed_keys: List[str], topk: int = 20) -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    for embed_key in embed_keys:
        configs.append({
            'group_name': 'line',
            'embed_keys': [embed_key],
            'topk': topk,
            'target': 'block',
        })
    for embed_key in embed_keys:
        configs.append({
            'group_name': 'block',
            'embed_keys': [embed_key],
            'topk': topk,
        })
    return configs


def _normalize_retriever_configs(retrieval: Dict[str, Any], embed_keys: List[str]) -> List[Dict[str, Any]]:
    retriever_configs = retrieval.get('retriever_configs')
    if retriever_configs is None:
        topk = int(retrieval.get('default_topk', 20))
        return _build_default_retriever_configs(embed_keys=embed_keys, topk=topk)
    if not isinstance(retriever_configs, list):
        raise ValueError('Config field `retrieval.retriever_configs` must be a list.')

    normalized_configs: List[Dict[str, Any]] = []
    for index, config in enumerate(retriever_configs, start=1):
        if not isinstance(config, dict):
            raise ValueError(f'Retriever config #{index} must be a mapping.')
        embed_keys_for_config = config.get('embed_keys')
        if not isinstance(embed_keys_for_config, list) or not embed_keys_for_config:
            raise ValueError(f'Retriever config #{index} must define a non-empty `embed_keys` list.')
        for embed_key in embed_keys_for_config:
            _resolve_embed_key(f'retrieval.retriever_configs[{index}].embed_keys', embed_key, embed_keys)
        normalized_configs.append(deepcopy(config))
    return normalized_configs


def _build_legacy_runtime_model_settings() -> RuntimeModelSettings:
    dense_model = os.getenv('DENSE_EMBED_MODEL', LEGACY_DENSE_EMBED_MODEL)
    sparse_model = os.getenv('SPARSE_EMBED_MODEL', LEGACY_SPARSE_EMBED_MODEL)
    llm_model = os.getenv('LLM_MODEL', LEGACY_LLM_MODEL)
    llm_instruct_model = os.getenv('LLM_INSTRUCT_MODEL', LEGACY_LLM_INSTRUCT_MODEL)
    reranker_model = os.getenv('RERANKER_MODEL', LEGACY_RERANKER_MODEL)

    embeddings: Dict[str, Any] = {LEGACY_DENSE_EMBED_KEY: dense_model}
    index_kwargs: List[Dict[str, Any]] = [
        _normalize_index_kwargs(LEGACY_DENSE_EMBED_KEY, None),
    ]
    retriever_configs: List[Dict[str, Any]] = [
        {
            'group_name': 'line',
            'embed_keys': [LEGACY_DENSE_EMBED_KEY],
            'topk': 20,
            'target': 'block',
        },
        {
            'group_name': 'block',
            'embed_keys': [LEGACY_DENSE_EMBED_KEY],
            'topk': 20,
        },
    ]
    file_search_embed_key = LEGACY_DENSE_EMBED_KEY
    embed_keys = [LEGACY_DENSE_EMBED_KEY]

    if sparse_model:
        embeddings[LEGACY_SPARSE_EMBED_KEY] = sparse_model
        index_kwargs.append(_normalize_index_kwargs(
            LEGACY_SPARSE_EMBED_KEY,
            LEGACY_SPARSE_EMBED_INDEX_KWARGS,
        ))
        retriever_configs[1:1] = [{
            'group_name': 'line',
            'embed_keys': [LEGACY_SPARSE_EMBED_KEY],
            'topk': 20,
            'target': 'block',
        }]
        retriever_configs.append({
            'group_name': 'block',
            'embed_keys': [LEGACY_SPARSE_EMBED_KEY],
            'topk': 20,
        })
        embed_keys.append(LEGACY_SPARSE_EMBED_KEY)
        file_search_embed_key = LEGACY_SPARSE_EMBED_KEY

    return RuntimeModelSettings(
        llm=llm_model,
        llm_instruct=llm_instruct_model,
        reranker=reranker_model,
        embeddings=embeddings,
        embed_keys=embed_keys,
        index_kwargs=index_kwargs,
        retriever_configs=retriever_configs,
        temp_doc_embed_key=LEGACY_DENSE_EMBED_KEY,
        file_search_embed_key=file_search_embed_key,
    )


@functools.lru_cache(maxsize=8)
def get_runtime_model_settings(config_path: str | None = None) -> RuntimeModelSettings:
    if not config_path and not has_explicit_runtime_model_config():
        return _build_legacy_runtime_model_settings()
    try:
        config = load_runtime_model_config(config_path)
    except Exception as exc:
        if config_path or has_explicit_runtime_model_config():
            raise
        lazyllm.LOG.warning(
            'Falling back to legacy auto_model settings because runtime model config is unavailable or invalid: %s',
            exc,
        )
        return _build_legacy_runtime_model_settings()
    roles = _get_runtime_roles(config)
    embeddings, embed_keys, index_kwargs = _normalize_embed_configs(roles)

    llm_config = _normalize_model_entry('llm', roles.get('llm'), 'llm')
    llm_instruct_raw = roles.get('llm_instruct') or roles.get('llm')
    llm_instruct_config = _normalize_model_entry('llm_instruct', llm_instruct_raw, 'llm')
    reranker_config = _normalize_model_entry('reranker', roles.get('reranker'), 'rerank')

    retrieval = config.get('retrieval', roles.get('retrieval', {})) or {}
    if not isinstance(retrieval, dict):
        raise ValueError('Config field `retrieval` must be a mapping.')

    temp_doc_embed_key = _resolve_embed_key(
        'retrieval.temp_doc_embed_key',
        retrieval.get('temp_doc_embed_key', embed_keys[0]),
        embed_keys,
    )
    file_search_embed_key = _resolve_embed_key(
        'retrieval.file_search_embed_key',
        retrieval.get('file_search_embed_key', _default_file_search_embed_key(embed_keys, index_kwargs)),
        embed_keys,
    )
    retriever_configs = _normalize_retriever_configs(retrieval, embed_keys)

    return RuntimeModelSettings(
        llm=llm_config,
        llm_instruct=llm_instruct_config,
        reranker=reranker_config,
        embeddings=embeddings,
        embed_keys=embed_keys,
        index_kwargs=index_kwargs,
        retriever_configs=retriever_configs,
        temp_doc_embed_key=temp_doc_embed_key,
        file_search_embed_key=file_search_embed_key,
    )


def build_model(model_config: Any):
    if isinstance(model_config, str):
        return AutoModel(model=model_config, config=get_auto_model_config_path())
    config = deepcopy(model_config)
    model_name = config.pop('model')
    config['model'] = model_name
    serialized_config = yaml.safe_dump(config, sort_keys=True)
    return AutoModel(model=model_name, config=_write_runtime_auto_model_config(serialized_config))


def build_embedding_models(settings: RuntimeModelSettings | None = None) -> Dict[str, Any]:
    active_settings = settings or get_runtime_model_settings()
    return {
        embed_key: build_model(model_config)
        for embed_key, model_config in active_settings.embeddings.items()
    }


def get_model(model, cfg=None):
    if isinstance(model, dict):
        config = deepcopy(model)
        model_name = config.pop('model', config.pop('name', None))
        if not model_name:
            raise ValueError('Inline model config must define `model`.')
        return AutoModel(model=model_name, config=False if cfg is None else cfg, **config)
    return AutoModel(model=model, config=cfg)
