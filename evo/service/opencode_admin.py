from __future__ import annotations
from typing import Any
from evo.apply.opencode import OpencodeOptions, OpencodeProviderConfig, apply_model
from evo.runtime.config import EvoConfig


def read_status(cfg: EvoConfig) -> dict[str, Any]:
    return _public(active_provider(cfg))


def write_config(cfg: EvoConfig, *, provider: str, model: str, api_key: str,
                 base_url: str | None = None, label: str | None = None) -> dict[str, Any]:
    active = active_provider(cfg)
    requested = OpencodeProviderConfig(
        _required(provider, 'provider'),
        _required(model, 'model'),
        api_key or '',
        base_url or '',
        label or provider,
    )
    same_target = (requested.provider, requested.model) == (active.provider, active.model)
    same_key = not requested.api_key or requested.api_key == active.api_key
    same_url = not requested.base_url or requested.base_url.rstrip('/') == active.base_url.rstrip('/')
    if not (same_target and same_key and same_url):
        raise ValueError(_ENV_ONLY)
    return _public(active)


def select_config(cfg: EvoConfig, *, provider: str, model: str | None = None) -> dict[str, Any]:
    active = active_provider(cfg)
    if _required(provider, 'provider') != active.provider or (model and _required(model, 'model') != active.model):
        raise ValueError(_ENV_ONLY)
    return _public(active)


def clear_config(cfg: EvoConfig) -> dict[str, Any]:
    return read_status(cfg)


def apply_options(cfg: EvoConfig, base: OpencodeOptions | None) -> OpencodeOptions:
    opts, active = base or OpencodeOptions(), active_provider(cfg)
    return OpencodeOptions(
        binary=opts.binary,
        model=f'{active.provider}/{active.model}',
        agent=opts.agent,
        variant=opts.variant,
        timeout_s=opts.timeout_s,
        provider_config=active)


def active_provider(cfg: EvoConfig) -> OpencodeProviderConfig:
    active = apply_model()
    return OpencodeProviderConfig(
        _required(active.provider, 'LAZYRAG_EVO_CODE_PROVIDER'),
        _required(active.model, 'LAZYRAG_EVO_CODE_MODEL'),
        active.api_key,
        active.base_url,
        active.label,
    )


def _required(value: str | None, name: str) -> str:
    if text := (value or '').strip():
        return text
    raise ValueError(f'{name} is required')


def _public(active: OpencodeProviderConfig) -> dict[str, Any]:
    return {
        'active': {
            'provider': active.provider,
            'model': active.model,
        },
        'providers': {
            active.provider: {
                'provider': active.provider,
                'label': active.label,
                'base_url': active.base_url,
                'api_key': _mask(active.api_key),
                'api_key_set': bool(active.api_key),
                'models': [active.model],
            }
        },
        'authenticated': bool(active.api_key),
    }


def _mask(value: str) -> str:
    return '' if not value else (value[:2] + '***' if len(value) <= 10 else value[:6] + '***' + value[-4:])


_ENV_ONLY = 'opencode config is controlled by LAZYRAG_EVO_CODE_* environment variables'
