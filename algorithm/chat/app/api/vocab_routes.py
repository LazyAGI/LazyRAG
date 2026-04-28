"""vocab_routes: 词表相关 API（支持多用户）。

后端在用户修改同义词族后调用此接口，算法服务从数据库重新加载对应用户的词表
并重建 AC 自动机。

POST /api/vocab/reload
    Body: {"create_user_id": "user_001"}
    Response: {"status": "ok", "vocab_size": <int>, "create_user_id": "<str>"}

POST /api/vocab/extract
    Body: {"create_user_id": "user_001"}
    Response: [{...backend action dict...}]
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from vocab import run_vocab_evolution
from vocab.vocab_manager import get_vocab_manager

router = APIRouter()


class VocabReloadRequest(BaseModel):
    create_user_id: str = ''


class VocabExtractRequest(BaseModel):
    create_user_id: str = ''


@router.post('/api/vocab/reload', summary='热更新指定用户的词表')
async def reload_vocab(body: VocabReloadRequest = VocabReloadRequest()):  # noqa: B008
    """从 lazyrag_vocab 表重新加载指定用户的词汇并重建 AC 自动机。

    - **create_user_id**: 用户ID，对应 lazyrag_vocab.create_user_id。
    """
    manager = get_vocab_manager(body.create_user_id)
    count = manager.reload()
    return {'status': 'ok', 'vocab_size': count, 'create_user_id': body.create_user_id}


@router.post('/api/vocab/extract', summary='触发词表自动进化抽取')
async def extract_vocab(body: VocabExtractRequest = VocabExtractRequest()):  # noqa: B008
    """按后端约定返回词表进化 action 列表。

    - **create_user_id**: 可选；为空时会扫描时间范围内全部有聊天记录的用户。
    """
    request = {'create_user_id': body.create_user_id} if body.create_user_id else None
    return run_vocab_evolution(request)
