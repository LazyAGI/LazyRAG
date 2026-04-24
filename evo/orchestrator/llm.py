from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Callable

from chat.pipelines.builders.get_models import get_automodel

from evo.runtime.config import EvoConfig
from evo.runtime.model_gateway import ModelGateway

LLMFactory = Callable[[], Callable[[str], AsyncIterator[str]]]


def _chunked(text: str, size: int = 64) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or ['']


def make_evo_llm(cfg: EvoConfig, *, chunk_size: int = 64) -> LLMFactory:
    role = cfg.model_config.llm_role
    gateway: ModelGateway[str] = ModelGateway(
        cfg.llm, name='evo-orchestrator-llm',
        logger=logging.getLogger('evo.orchestrator.llm'),
    )

    def factory() -> Callable[[str], AsyncIterator[str]]:
        client = get_automodel(role)

        async def call(prompt: str) -> AsyncIterator[str]:
            text = await asyncio.to_thread(
                gateway.call, lambda: client(prompt),
                cache_key=prompt, agent='orchestrator')
            for chunk in _chunked(text or '', chunk_size):
                await asyncio.sleep(0)
                yield chunk
        return call

    return factory
