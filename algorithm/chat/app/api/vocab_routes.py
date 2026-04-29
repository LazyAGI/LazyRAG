"""vocab_routes: 词表相关 API（支持多用户）。

后端在用户修改同义词族后调用此接口，算法服务从数据库重新加载对应用户的词表
并重建 AC 自动机。

POST /api/vocab/reload
    Body: {"create_user_id": "user_001"}
    Response: {"status": "ok", "vocab_size": <int>, "create_user_id": "<str>"}

POST /api/vocab/extract
    Body: {"create_user_id": "user_001"}
    Response: 204 No Content
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from lazyllm import LOG
from pydantic import BaseModel

from vocab import run_vocab_evolution
from vocab.vocab_manager import get_vocab_manager

router = APIRouter()


class VocabUserRequest(BaseModel):
    create_user_id: str = ''


def _target_label(request: dict | None) -> str:
    if not request:
        return '<all-users>'
    return (request.get('create_user_id') or '').strip() or '<all-users>'


def _run_vocab_evolution_task(request: dict | None) -> None:
    target_label = _target_label(request)
    LOG.info(f'[VocabRoutes] extract started create_user_id={target_label!r}')
    try:
        actions = run_vocab_evolution(request)
    except Exception as exc:
        LOG.error(f'[VocabRoutes] extract failed create_user_id={target_label!r} error={exc}')
        return
    LOG.info(f'[VocabRoutes] extract finished create_user_id={target_label!r} action_count={len(actions)}')


@router.post('/api/vocab/reload', summary='热更新指定用户的词表')
async def reload_vocab(body: VocabUserRequest | None = None):
    """从 lazyrag_vocab 表重新加载指定用户的词汇并重建 AC 自动机。

    - **create_user_id**: 用户ID，对应 lazyrag_vocab.create_user_id。
    """
    body = body or VocabUserRequest()
    resolved_create_user_id = body.create_user_id.strip()
    LOG.info(f'[VocabRoutes] reload requested create_user_id={resolved_create_user_id!r}')
    try:
        manager = get_vocab_manager(resolved_create_user_id)
        count = manager.reload()
    except Exception as exc:
        LOG.error(f'[VocabRoutes] reload failed create_user_id={resolved_create_user_id!r} error={exc}')
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='vocab reload failed') from exc
    return {'status': 'ok', 'vocab_size': count, 'create_user_id': resolved_create_user_id}


@router.post('/api/vocab/extract', summary='触发词表自动进化抽取', status_code=status.HTTP_204_NO_CONTENT)
async def extract_vocab(
    background_tasks: BackgroundTasks,
    body: VocabUserRequest | None = None,
):
    """按后端约定触发词表进化，并主动把 action_list 回推给 core。

    - **create_user_id**: 可选；为空时会扫描时间范围内全部有聊天记录的用户。
    """
    body = body or VocabUserRequest()
    resolved_create_user_id = body.create_user_id.strip()
    request = {'create_user_id': resolved_create_user_id} if resolved_create_user_id else None
    LOG.info(f'[VocabRoutes] extract queued create_user_id={_target_label(request)!r}')
    background_tasks.add_task(_run_vocab_evolution_task, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
