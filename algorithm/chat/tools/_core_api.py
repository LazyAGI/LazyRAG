from __future__ import annotations

from typing import Any, Dict, Optional

import lazyllm
import requests

from config import config as _cfg


def core_api_base_url(agentic_config: Optional[Dict[str, Any]] = None) -> str:
    config = agentic_config if isinstance(agentic_config, dict) else None
    base_url = config.get('core_api_url') if config else None
    if base_url is None:
        base_url = _cfg['core_api_url']
    return str(base_url or '').strip().rstrip('/')


def core_api_endpoint(path: str, agentic_config: Optional[Dict[str, Any]] = None) -> str:
    base_url = core_api_base_url(agentic_config)
    if not base_url:
        raise RuntimeError("'core_api_url' is required in config.")
    normalized_path = '/' + path.lstrip('/')
    return f'{base_url}{normalized_path}'


def session_id(agentic_config: Optional[Dict[str, Any]] = None) -> str:
    config = agentic_config if isinstance(agentic_config, dict) else lazyllm.globals['agentic_config']
    return str(config.get('session_id') or lazyllm.globals._sid or '').strip()


def post_core_api(
    path: str,
    payload: Dict[str, Any],
    agentic_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = agentic_config if isinstance(agentic_config, dict) else lazyllm.globals['agentic_config']
    url = core_api_endpoint(path, config)
    timeout = int(config.get('core_api_timeout', _cfg['core_api_timeout']))
    with requests.sessions.Session() as session:
        session.trust_env = False
        response = session.post(url, json=payload, timeout=timeout)

    try:
        body = response.json()
    except ValueError:
        body = {'text': response.text}

    if not response.ok:
        msg = (
            body.get('msg') or body.get('message')
            if isinstance(body, dict)
            else response.text
        )
        raise RuntimeError(f'POST {url} failed with HTTP {response.status_code}: {msg}')

    if isinstance(body, dict) and body.get('code') not in (None, 0):
        msg = body.get('msg') or body.get('message') or body
        raise RuntimeError(f'POST {url} failed: {msg}')

    return {
        'persisted': 'core_api',
        'url': url,
        'response': body,
    }
