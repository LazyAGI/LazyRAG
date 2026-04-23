from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from chat.pipelines.builders.get_models import get_automodel

router = APIRouter(prefix='/internal', tags=['internal'])
log = logging.getLogger('chat.internal')

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.getenv('CHAT_INTERNAL_WORKERS', '4')),
    thread_name_prefix='chat-internal',
)
_DEFAULT_MAX_TOKENS = int(os.getenv('CHAT_INTERNAL_MAX_TOKENS', '32768'))
_DEFAULT_TEMPERATURE = (float(os.environ['CHAT_INTERNAL_TEMPERATURE'])
                        if os.getenv('CHAT_INTERNAL_TEMPERATURE') else None)


def _check_token(x_internal_token: str = Header(default='')) -> None:
    expected = os.getenv('EVO_CHAT_INTERNAL_TOKEN', '')
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=403, detail='invalid internal token')


class LlmCall(BaseModel):
    role: str
    user_text: str
    system_prompt: str | None = None


class EmbedCall(BaseModel):
    role: str
    texts: list[str]


def _normalize(out: Any) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, dict):
        c = out.get('content')
        if isinstance(c, str) and c.strip():
            return c
        return json.dumps(out, ensure_ascii=False)
    return str(out)


def _to_floats(v: Any) -> list[float]:
    if isinstance(v, str):
        v = json.loads(v)
    return [float(x) for x in v]


def _llm_kwargs() -> dict[str, Any]:
    kw: dict[str, Any] = {'max_tokens': _DEFAULT_MAX_TOKENS}
    if _DEFAULT_TEMPERATURE is not None:
        kw['temperature'] = _DEFAULT_TEMPERATURE
    return kw


def _call(llm: Any, text: str) -> Any:
    kw = _llm_kwargs()
    try:
        return llm(text, **kw)
    except Exception as exc:
        log.warning('llm(text, **%s) failed (%s); retrying without kwargs',
                    list(kw), exc)
        return llm(text)


def _llm_sync(req: LlmCall) -> str:
    llm = get_automodel(req.role)
    if req.system_prompt:
        try:
            from lazyllm.components import ChatPrompter
            llm = llm.share(prompt=ChatPrompter(instruction=req.system_prompt))
        except Exception:
            return _normalize(_call(
                llm, f'{req.system_prompt}\n\n---\n\n{req.user_text}'))
    return _normalize(_call(llm, req.user_text))


def _embed_sync(req: EmbedCall) -> list[list[float]]:
    embed = get_automodel(req.role)
    return [_to_floats(embed(t)) for t in req.texts]


async def _run_in_executor(fn, req, label: str):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_EXECUTOR, fn, req)
    except Exception as exc:
        log.exception('%s failed: role=%s', label, req.role)
        raise HTTPException(status_code=500,
                            detail=f'{type(exc).__name__}: {exc}') from exc


@router.post('/llm/call', dependencies=[Depends(_check_token)],
             summary='Synchronous LLM call (used by evo agents).')
async def llm_call(req: LlmCall) -> dict[str, str]:
    return {'output': await _run_in_executor(_llm_sync, req, 'internal/llm/call')}


@router.post('/embed/call', dependencies=[Depends(_check_token)],
             summary='Batch text embedding (used by evo).')
async def embed_call(req: EmbedCall) -> dict[str, list[list[float]]]:
    return {'vectors': await _run_in_executor(_embed_sync, req, 'internal/embed/call')}
