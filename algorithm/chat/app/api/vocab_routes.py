"""vocab_routes: Vocabulary-related API (multi-user support).

The backend calls this endpoint after a user modifies synonym groups; the algorithm
service reloads the vocabulary for the corresponding user from the database and
rebuilds the AC automaton.

POST /api/vocab/reload
    Body: {"create_user_id": "user_001"}
    Response: {"status": "ok", "vocab_size": <int>, "create_user_id": "<str>"}

POST /api/vocab/extract
    Body: {"create_user_id": "user_001"}
    Response: 204 No Content
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Response, status
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
    return (request.get('create_user_id') or '<all-users>')


@router.post('/api/vocab/reload')
async def reload_vocab(request: VocabUserRequest):
    create_user_id = (request.create_user_id or '').strip() or None
    manager = get_vocab_manager(create_user_id)
    manager.reload()
    LOG.info(f'[VocabRoutes] reload done create_user_id={_target_label(request.model_dump())!r} '
             f'vocab_size={manager.vocab_size}')
    return {
        'status': 'ok',
        'vocab_size': manager.vocab_size,
        'create_user_id': create_user_id or '',
    }


def _run_vocab_evolution_task(request: dict | None) -> None:
    try:
        resolved_create_user_id = (request or {}).get('create_user_id') or None
        run_vocab_evolution(
            create_user_id=resolved_create_user_id,
        )
    except Exception as exc:
        LOG.error(f'[VocabRoutes] vocab evolution failed: {exc}')


@router.post('/api/vocab/extract', status_code=status.HTTP_204_NO_CONTENT)
async def extract_vocab(
    background_tasks: BackgroundTasks,
    request: VocabUserRequest,
):
    resolved_create_user_id = (request.create_user_id or '').strip() or None
    request_dict = {'create_user_id': resolved_create_user_id} if resolved_create_user_id else None
    LOG.info(f'[VocabRoutes] extract queued create_user_id={_target_label(request_dict)!r}')
    background_tasks.add_task(_run_vocab_evolution_task, request_dict)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
