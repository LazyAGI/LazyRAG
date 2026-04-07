import os

import httpx
from fastapi import APIRouter

router = APIRouter()


@router.get('/health', summary='Health check')
@router.get('/api/health', summary='Health check (API path)')
async def health():
    doc_url = os.getenv('LAZYRAG_DOCUMENT_SERVER_URL', 'http://localhost:8000')
    check_url = doc_url.rstrip('/') + '/'
    status = {'document_server_url': doc_url, 'document_server_reachable': None}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(check_url)
        status['document_server_reachable'] = True
    except Exception as e:
        status['document_server_reachable'] = False
        status['document_server_error'] = str(e)
    return status
