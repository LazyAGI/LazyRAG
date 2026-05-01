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


@router.post('/api/vocab/reload', summary='Hot-reload vocabulary for the specified user')
async def reload_vocab(body: VocabUserRequest | None = None):
    """Reload vocabulary from the database for the specified user and rebuild the AC automaton.

    - **create_user_id**: User ID, corresponds to core.public.words.create_user_id.
    """
    body = body or VocabUserRequest()
    resolved_create_user_id = body.create_user_id.strip()
    LOG.info(f'[VocabRoutes] reload requested create_user_id={resolved_create_user_id!r}')
    try:
        manager = get_vocab_manager(resolved_create_user_id)
        manager.reload()
    except Exception as exc:
        LOG.error(f'[VocabRoutes] reload failed create_user_id={resolved_create_user_id!r} error={exc}')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Vocab reload failed: {exc}',
        )
    LOG.info(
        f'[VocabRoutes] reload done create_user_id={resolved_create_user_id!r} '
        f'vocab_size={manager.vocab_size}'
    )
    return {
        'status': 'ok',
        'vocab_size': manager.vocab_size,
        'create_user_id': resolved_create_user_id,
    }


@router.post('/api/vocab/extract', status_code=status.HTTP_204_NO_CONTENT,
             summary='Trigger vocabulary evolution and push action list back to core')
async def extract_vocab(
    background_tasks: BackgroundTasks,
    body: VocabUserRequest | None = None,
):
    """Trigger vocabulary evolution per backend convention and push the action_list back to core.

    - **create_user_id**: Optional; when empty, scans all users with chat history in the time range.
    """
    body = body or VocabUserRequest()
    resolved_create_user_id = body.create_user_id.strip()
    request = {'create_user_id': resolved_create_user_id} if resolved_create_user_id else None
    LOG.info(f'[VocabRoutes] extract queued create_user_id={_target_label(request)!r}')
    background_tasks.add_task(_run_vocab_evolution_task, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
