"""vocab_routes: 词表热更新 API。

POST /api/vocab/reload
    Body（可选）: {"file_path": "/path/to/vocab.json"}
    Response:    {"status": "ok", "vocab_size": <int>}
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from vocab.vocab_manager import get_vocab_manager

router = APIRouter()


class VocabReloadRequest(BaseModel):
    file_path: Optional[str] = None


@router.post('/api/vocab/reload', summary='热更新词表')
async def reload_vocab(body: VocabReloadRequest = VocabReloadRequest()):  # noqa: B008
    """重新从词表文件加载词汇并重建 AC 自动机。

    - **file_path**: 可选，指定新词表文件路径；不传则沿用当前配置路径。
    """
    manager = get_vocab_manager()
    count = manager.reload(file_path=body.file_path)
    return {'status': 'ok', 'vocab_size': count}
