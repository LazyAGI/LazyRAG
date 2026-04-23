"""vocab_routes: 词表热更新 API（支持多用户）。

后端在用户修改同义词族后调用此接口，算法服务从数据库重新加载对应用户的词表
并重建 AC 自动机。

POST /api/vocab/reload
    Body: {"user_id": "user_001"}
    Response: {"status": "ok", "vocab_size": <int>, "user_id": "<str>"}
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from vocab.vocab_manager import get_vocab_manager

router = APIRouter()


class VocabReloadRequest(BaseModel):
    user_id: str = ''


@router.post('/api/vocab/reload', summary='热更新指定用户的词表')
async def reload_vocab(body: VocabReloadRequest = VocabReloadRequest()):  # noqa: B008
    """从 lazyrag_vocab 表重新加载指定用户的词汇并重建 AC 自动机。

    - **user_id**: 用户ID（对应 lazyrag_vocab.create_user_id）。
    """
    manager = get_vocab_manager(body.user_id)
    count = manager.reload()
    return {'status': 'ok', 'vocab_size': count, 'user_id': body.user_id}
