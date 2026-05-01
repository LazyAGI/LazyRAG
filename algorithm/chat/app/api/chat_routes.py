from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Request
from chat.app.core.chat_service import handle_chat
from chat.config import DEFAULT_CHAT_DATASET

router = APIRouter()


@router.post('/api/chat', summary='与知识库对话')
@router.post('/api/chat/stream', summary='与知识库对话')
async def chat(
    query: Annotated[str, Body(description='用户问题')],
    history: Annotated[
        Optional[List[Dict[str, Any]]],
        Body(description='历史对话（每项可含 role、content）'),
    ] = None,
    session_id: Annotated[str, Body(description='会话 ID')] = 'session_id',
    filters: Annotated[Optional[Dict[str, Any]], Body(description='检索过滤条件')] = None,
    files: Annotated[Optional[List[str]], Body(description='上传临时文件')] = None,
    debug: Annotated[Optional[bool], Body(description='是否开启debug模式')] = False,
    reasoning: Annotated[Optional[bool], Body(description='是否开启推理')] = False,
    databases: Annotated[Optional[List[Dict]], Body(description='关联数据库')] = None,
    dataset: Annotated[Optional[str], Body(description='数据库名称')] = DEFAULT_CHAT_DATASET,
    priority: Annotated[
        Optional[int],
        Body(description='请求优先级，用于vllm调度。数值越大优先级越高'),
    ] = None,
    available_tools: Annotated[Optional[List[str]], Body(description='可用工具列表')] = None,
    available_skills: Annotated[Optional[List[str]], Body(description='可用技能列表')] = None,
    memory: Annotated[Optional[str], Body(description='memory 内容')] = None,
    user_preference: Annotated[Optional[str], Body(description='user_preference 内容')] = None,
    use_memory: Annotated[Optional[bool], Body(description='是否使用 memory')] = True,
    create_user_id: Annotated[Optional[str], Body(description='用户ID，用于加载该用户的专有词表')] = None,
    trace: Annotated[Optional[bool], Body(description='是否记录 trace（仅管理员调试时开启）')] = False,
    *,
    request: Request,
):
    is_stream = request.url.path.endswith('/stream')

    return await handle_chat(
        query=query,
        history=history,
        session_id=session_id,
        filters=filters,
        files=files,
        debug=debug,
        reasoning=reasoning,
        databases=databases,
        dataset=dataset,
        priority=priority,
        trace=bool(trace),
        available_tools=available_tools,
        available_skills=available_skills,
        memory=memory,
        user_preference=user_preference,
        use_memory=use_memory,
        is_stream=is_stream,
        create_user_id=(create_user_id or '').strip(),
    )
