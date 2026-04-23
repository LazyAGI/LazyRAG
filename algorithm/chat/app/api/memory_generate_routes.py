from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from chat.pipelines.memory_generate import (
    BadRequestError,
    MemoryType,
    UnprocessableContentError,
    generate_memory_content,
)

router = APIRouter()


class SuggestionPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str = Field(..., description='建议标题')
    content: str = Field(..., description='自然语言修改建议')
    reason: Optional[str] = Field(default=None, description='提议理由')
    outdated: Optional[bool] = Field(default=None, description='建议是否已过期')


class GeneratePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    content: str = Field(..., description='目标内容当前完整文本')
    suggestions: Optional[List[SuggestionPayload]] = Field(
        default=None,
        description='待合入建议列表',
    )
    user_instruct: str = Field(..., description='用户直接下达的自然语言指令')


def _ok(content: str) -> Dict[str, Any]:
    return {'code': 0, 'msg': 'ok', 'data': {'content': content}}


def _fail(status_code: int, msg: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={'code': status_code, 'msg': msg, 'data': None},
    )


def _handle_generate(memory_type: MemoryType, payload: GeneratePayload):
    try:
        generated = generate_memory_content(
            memory_type=memory_type,
            content=payload.content,
            suggestions=[s.model_dump() for s in payload.suggestions] if payload.suggestions else None,
            user_instruct=payload.user_instruct,
        )
        return _ok(generated)
    except BadRequestError as exc:
        return _fail(400, str(exc))
    except UnprocessableContentError as exc:
        return _fail(422, str(exc))
    except Exception as exc:
        return _fail(500, f'generate failed: {exc}')


@router.post('/skill/generate', summary='生成新的 skill content')
async def generate_skill(payload: GeneratePayload):
    return _handle_generate('skill', payload)


@router.post('/memory/generate', summary='生成新的 memory content')
async def generate_memory(payload: GeneratePayload):
    return _handle_generate('memory', payload)


@router.post('/user_preference/generate', summary='生成新的 user_preference content')
async def generate_user_preference(payload: GeneratePayload):
    return _handle_generate('user_preference', payload)
