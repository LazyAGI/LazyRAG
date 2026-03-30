import os
import time
import asyncio
from typing import List, Optional, Dict, Any, TypeVar

from pydantic import BaseModel, Field
from fastapi import Body, FastAPI, Request

import lazyllm
from lazyllm.tools.rag import Document
from lazyllm import LOG

app = FastAPI()
M = TypeVar('M')


class BaseResponse(BaseModel):
    code: int = Field(200, description='API status code')
    msg: str = Field('success', description='API status message')
    data: Optional[M] = Field(None, description='API data')

    class Config:
        schema_extra = {'example': {'code': 200, 'msg': 'success', 'data': None}}


class ChatResponse(BaseResponse):
    cost: float = Field(0.0, description='API cost time (seconds)')

    class Config:
        schema_extra = {
            'example': {
                'code': 200,
                'msg': 'success',
                'data': None,
                'cost': 0.1,
            }
        }


class History(BaseModel):
    role: str = Field('assistant', description='Role: user or assistant')
    content: str = Field('', description='Message content')


def _normalize_history(raw: Any) -> List[History]:
    """Accept list, empty dict, or None from client/proxy (e.g. Kong may send history as {})."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, History):
            out.append(item)
        elif isinstance(item, dict):
            out.append(History(role=item.get('role', 'assistant'), content=item.get('content', '')))
        else:
            continue
    return out


MAX_CONCURRENCY = int(os.getenv('LAZYRAG_MAX_CONCURRENCY', 10))
rag_sem = asyncio.Semaphore(MAX_CONCURRENCY)


doc = Document(url=os.getenv('LAZYRAG_DOCUMENT_SERVER_URL', 'http://localhost:8000'), name='general_algo')
_default_prompt = (
    'You are a RAG assistant. Answer the user question `{query}` using '
    'history `{history}` and references `{references}`.'
)
llm = lazyllm.OnlineChatModule().prompt(
    os.getenv('LAZYRAG_CHAT_PROMPT', _default_prompt)
)
r1 = lazyllm.Retriever(
    doc=doc, group_name='block', topk=25, output_format='content', join='\n\n'
)


def _history_to_list(history: List[History]) -> list:
    try:
        return [h.model_dump() for h in history]
    except AttributeError:
        return [h.dict() for h in history]


def _history_for_prompt(history: List[History]) -> str:
    """Format history as string for prompt template (template uses str.replace)."""
    items = _history_to_list(history)
    if not items:
        return ''
    return '\n'.join(f"{h.get('role', '')}: {h.get('content', '')}" for h in items)


def ppl(
    query: str,
    history: List[History],
    filters: Optional[Dict[str, Any]],
    files: Optional[List[str]],
    debug: Optional[bool],
    reasoning: Optional[bool],
    databases: Optional[List[Dict]],
    priority: Optional[int],
):
    refs = r1(query=query, filters=filters)
    # Prompt template uses str.replace(); all format values must be str, not list
    history_str = _history_for_prompt(history)
    refs_str = refs if isinstance(refs, str) else '\n\n'.join(refs) if refs else ''
    return llm(dict(query=query, history=history_str, references=refs_str))


@app.get('/health', summary='Health check')
@app.get('/api/health', summary='Health check (API path)')
async def health():
    """Health check; optionally checks document server connectivity."""
    doc_url = os.getenv('LAZYRAG_DOCUMENT_SERVER_URL', 'http://localhost:8000')
    status = {'document_server_url': doc_url, 'document_server_reachable': None}
    try:
        import urllib.request
        req = urllib.request.Request(doc_url.rstrip('/') + '/', method='GET')
        urllib.request.urlopen(req, timeout=3)
        status['document_server_reachable'] = True
    except Exception as e:
        status['document_server_reachable'] = False
        status['document_server_error'] = str(e)
    return status


@app.post('/api/chat', summary='与知识库对话')
@app.post('/api/chat/stream', summary='与知识库对话')
async def chat(
    query: str = Body(..., description='用户问题'),  # noqa: B008
    history: Any = Body(default=None, description='历史对话，可为 list 或省略（代理可能传为 {}）'),  # noqa: B008
    session_id: str = Body('session_id', description='会话 ID'),  # noqa: B008
    filters: Optional[Dict[str, Any]] = Body(None, description='检索过滤条件'),  # noqa: B008
    files: Optional[List[str]] = Body(None, description='上传临时文件'),  # noqa: B008
    debug: Optional[bool] = Body(False, description='是否开启debug模式'),  # noqa: B008
    reasoning: Optional[bool] = Body(False, description='是否开启推理'),  # noqa: B008
    databases: Optional[List[Dict]] = Body([], description='关联数据库'),  # noqa: B008
    priority: Optional[int] = Body(  # noqa: B008
        None,
        description='请求优先级，用于vllm调度。数值越大优先级越高，默认从环境变量LAZYRAG_LLM_PRIORITY读取',
    ),
    *,
    request: Request,
) -> ChatResponse:
    cost = 0.0
    result = None
    history_list = _normalize_history(history)
    is_stream = request.url.path.endswith('/stream')  # noqa: F841
    effective_priority = int(os.getenv('LAZYRAG_LLM_PRIORITY', '0')) if priority is None else priority
    try:
        t0 = time.perf_counter()
        async with rag_sem:
            lazyllm.globals._init_sid(sid=session_id)
            result = await asyncio.to_thread(
                ppl,
                query=query,
                history=history_list,
                filters=filters,
                files=files,
                debug=debug,
                reasoning=reasoning,
                databases=databases,
                priority=effective_priority,
            )
        cost = time.perf_counter() - t0
        return ChatResponse(code=200, msg='success', data=result, cost=cost)
    except Exception as exc:
        LOG.exception(exc)
        return ChatResponse(code=500, msg=f'chat service failed: {exc}', cost=cost)


if __name__ == '__main__':
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='0.0.0.0', help='listen host')
    parser.add_argument('--port', type=int, default=8046, help='listen port')
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
