from __future__ import annotations
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any
from evo.apply.opencode import OpencodeOptions, OpencodeProviderConfig
from evo.runtime.config import EvoConfig
from evo.runtime.fs import atomic_write_json

_DEFAULT_DEEPSEEK_KEY = 'sk-74c7d7e099d34f25ac801d05994ab694'


def read_status(cfg: EvoConfig) -> dict[str, Any]:
    data = _read_config(cfg)
    return _public_config(data)


def write_config(
    cfg: EvoConfig, *, provider: str, model: str, api_key: str, base_url: str | None = None, label: str | None = None
) -> dict[str, Any]:
    provider = _clean(provider, 'provider')
    model = _clean(model, 'model')
    data = _read_config(cfg)
    providers = data.setdefault('providers', {})
    current = dict(providers.get(provider) or {})
    current.update(
        {
            'provider': provider,
            'label': label or current.get('label') or provider,
            'base_url': base_url or current.get('base_url') or _default_base_url(provider),
            'api_key': api_key,
        }
    )
    models = list(current.get('models') or [])
    if model not in models:
        models.append(model)
    current['models'] = models
    providers[provider] = current
    data['active'] = {'provider': provider, 'model': model}
    _write_config(cfg, data)
    return _public_config(data)


def select_config(cfg: EvoConfig, *, provider: str, model: str | None = None) -> dict[str, Any]:
    provider = _clean(provider, 'provider')
    data = _read_config(cfg)
    item = (data.get('providers') or {}).get(provider)
    if not item:
        raise ValueError(f'unknown opencode provider: {provider}')
    selected = model or _first_model(item)
    selected = _clean(selected, 'model')
    if selected not in (item.get('models') or []):
        raise ValueError(f'unknown model {selected!r} for provider {provider!r}')
    data['active'] = {'provider': provider, 'model': selected}
    _write_config(cfg, data)
    return _public_config(data)


def clear_config(cfg: EvoConfig) -> dict[str, Any]:
    path = _path(cfg)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return _public_config(_default_config())


def apply_options(cfg: EvoConfig, base: OpencodeOptions | None) -> OpencodeOptions:
    opts = base or OpencodeOptions()
    active = active_provider(cfg)
    return OpencodeOptions(
        binary=opts.binary,
        model=f'{active.provider}/{active.model}',
        agent=opts.agent,
        variant=opts.variant,
        timeout_s=opts.timeout_s,
        provider_config=active,
    )


def active_provider(cfg: EvoConfig) -> OpencodeProviderConfig:
    data = _read_config(cfg)
    active = data.get('active') or {}
    provider = active.get('provider') or 'deepseek'
    item = (data.get('providers') or {}).get(provider)
    if not item:
        item = _default_provider(provider)
    model = active.get('model') or _first_model(item)
    return OpencodeProviderConfig(
        provider=provider,
        model=model,
        api_key=str(item.get('api_key') or ''),
        base_url=str(item.get('base_url') or _default_base_url(provider)),
        label=str(item.get('label') or provider),
    )


def _path(cfg: EvoConfig) -> Path:
    return cfg.storage.base_dir / 'state' / 'opencode_config.json'


def _read_config(cfg: EvoConfig) -> dict[str, Any]:
    path = _path(cfg)
    if not path.is_file():
        return _default_config()
    data = json.loads(path.read_text(encoding='utf-8'))
    return _merge_defaults(data)


def _write_config(cfg: EvoConfig, data: dict[str, Any]) -> None:
    atomic_write_json(_path(cfg), data)


def _default_config() -> dict[str, Any]:
    return {
        'active': {'provider': 'deepseek', 'model': 'deepseek-chat'},
        'providers': {
            'deepseek': {
                'provider': 'deepseek',
                'label': 'DeepSeek',
                'base_url': os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
                'api_key': os.getenv('DEEPSEEK_API_KEY', _DEFAULT_DEEPSEEK_KEY),
                'models': ['deepseek-chat'],
            },
            'maas': {
                'provider': 'maas',
                'label': 'MAAS',
                'base_url': os.getenv('MAAS_BASE_URL', 'http://106.75.235.251:9000/v1/'),
                'api_key': os.getenv('LAZYRAG_MAAS_API_KEY', ''),
                'models': [os.getenv('MAAS_MODEL_NAME', 'minimax-m27')],
            },
        },
    }


def _merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    merged = _default_config()
    providers = merged['providers']
    providers.update(deepcopy(data.get('providers') or {}))
    active = data.get('active') or merged['active']
    merged['active'] = active
    return merged


def _default_provider(provider: str) -> dict[str, Any]:
    return _default_config()['providers'].get(
        provider,
        {'provider': provider, 'label': provider, 'base_url': _default_base_url(provider), 'api_key': '', 'models': []},
    )


def _default_base_url(provider: str) -> str:
    if provider == 'deepseek':
        return 'https://api.deepseek.com'
    if provider == 'maas':
        return 'http://106.75.235.251:9000/v1/'
    return ''


def _first_model(item: dict[str, Any]) -> str:
    models = item.get('models') or []
    if not models:
        raise ValueError('provider has no models')
    return str(models[0])


def _clean(value: str | None, name: str) -> str:
    text = (value or '').strip()
    if not text:
        raise ValueError(f'{name} is required')
    return text


def _public_config(data: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(data)
    for item in (out.get('providers') or {}).values():
        key = item.get('api_key') or ''
        item['api_key_set'] = bool(key)
        item['api_key'] = _mask(key)
    active = out.get('active') or {}
    provider = active.get('provider')
    item = (data.get('providers') or {}).get(provider) or {}
    out['authenticated'] = bool(item.get('api_key'))
    return out


def _mask(value: str) -> str:
    if not value:
        return ''
    if len(value) <= 10:
        return value[:2] + '***'
    return value[:6] + '***' + value[-4:]
