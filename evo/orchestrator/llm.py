from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncIterator, Callable, Iterator

import requests
from evo.runtime.config import EvoConfig
from evo.runtime.model_gateway import ModelGateway

LLMFactory = Callable[[], Callable[[str], AsyncIterator[str]]]


def get_automodel(role: str):
    from chat.pipelines.builders.get_models import get_automodel as _ga

    return _ga(role)


def _chunked(text: str, size: int = 64) -> list[str]:
    return [text[i: i + size] for i in range(0, len(text), size)] or ['']


def make_evo_llm(cfg: EvoConfig, *, chunk_size: int = 64) -> LLMFactory:
    role = cfg.model_config.llm_role
    gateway: ModelGateway[str] = ModelGateway(
        cfg.llm, name='evo-orchestrator-llm', logger=logging.getLogger('evo.orchestrator.llm')
    )

    def factory() -> Callable[[str], AsyncIterator[str]]:
        client = get_automodel(role)

        async def call(prompt: str) -> AsyncIterator[str]:
            text = await asyncio.to_thread(gateway.call, lambda: client(prompt), cache_key=prompt, agent='orchestrator')
            for chunk in _chunked(text or '', chunk_size):
                await asyncio.sleep(0)
                yield chunk

        return call

    return factory


def make_evo_stream_llm(cfg: EvoConfig) -> Callable[[str, Callable[[], bool]], Iterator[str]]:
    role = cfg.model_config.llm_role
    timeout = cfg.llm.http_timeout_s

    def stream(prompt: str, cancel_requested: Callable[[], bool]) -> Iterator[str]:
        from chat.utils.load_config import get_role_config

        model, config = get_role_config(role)
        base_url = str(config.get('url') or '').rstrip('/')
        if not base_url:
            raise RuntimeError(f'model role {role!r} has no url')
        url = base_url if base_url.endswith('/chat/completions') else f'{base_url}/chat/completions'
        headers = {'Content-Type': 'application/json'}
        api_key = config.get('api_key')
        if api_key and not config.get('skip_auth'):
            headers['Authorization'] = f'Bearer {api_key}'
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': float(config.get('temperature', 0.01) or 0.01),
            'max_tokens': int(config.get('max_tokens', 4096) or 4096),
            'stream': True,
        }
        session = requests.Session()
        session.trust_env = False
        with session.post(url, headers=headers, json=payload, stream=True, timeout=(10, timeout)) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if cancel_requested():
                    resp.close()
                    raise RuntimeError('MESSAGE_CANCELLED')
                if not line:
                    continue
                if line.startswith('data:'):
                    line = line[5:].strip()
                if line == '[DONE]':
                    break
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = ((data.get('choices') or [{}])[0].get('delta') or {}).get('content')
                if delta:
                    yield str(delta)

    return stream
