import os
from pathlib import Path
from typing import Any, Dict

import lazyllm
import yaml
from lazyllm import AutoModel

from .embed import BgeM3Embed

DEFAULT_AUTO_MODEL_CONFIG_PATH = Path(__file__).resolve().parents[2] / 'configs' / 'auto_model.yaml'


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


def _get_model_entry(model_name: str, config_path: str | None = None) -> Dict[str, Any]:
    cfg = load_auto_model_config(config_path)
    entries = cfg.get(model_name)
    if not entries:
        raise KeyError(f'Model config `{model_name}` not found in `{config_path or get_auto_model_config_path()}`')
    if not isinstance(entries, list):
        raise ValueError(f'Model config `{model_name}` must be a list, got {type(entries)!r}')
    entry = entries[0] if entries else None
    if not isinstance(entry, dict):
        raise ValueError(f'Model config `{model_name}` entry must be a dict, got {type(entry)!r}')
    return entry


def build_bge_m3_embed(model_name: str, config_path: str | None = None) -> BgeM3Embed:
    entry = _get_model_entry(model_name, config_path)
    embed_url = entry.get('url')
    if not embed_url:
        raise ValueError(f'Model config `{model_name}` missing `url`')

    return BgeM3Embed(
        embed_url=embed_url,
        embed_model_name=entry.get('name', model_name),
        api_key=entry.get('api_key'),
        skip_auth=entry.get('skip_auth', True),
    )


def get_model(model_name, cfg):
    m = AutoModel(model=model_name, config=cfg)
    return m
