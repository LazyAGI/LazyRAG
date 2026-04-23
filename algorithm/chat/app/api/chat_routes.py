from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Request
from chat.config import DEFAULT_CHAT_DATASET
from chat.app.core.chat_service import handle_chat

router = APIRouter()


@router.post('/api/chat', summary='与知识库对话')
@router.post('/api/chat/stream', summary='与知识库对话')
async def chat(
    query: str = Body(..., description='用户问题'),  # noqa: B008
    history: Optional[List[Dict[str, Any]]] = Body(default=None, description='历史对话（每项可含 role、content）'),  # noqa: B008
    session_id: str = Body('session_id', description='会话 ID'),  # noqa: B008
    filters: Optional[Dict[str, Any]] = Body(None, description='检索过滤条件'),  # noqa: B008
    files: Optional[List[str]] = Body(None, description='上传临时文件'),  # noqa: B008
    debug: Optional[bool] = Body(False, description='是否开启debug模式'),  # noqa: B008
    reasoning: Optional[bool] = Body(False, description='是否开启推理'),  # noqa: B008
    databases: Optional[List[Dict]] = Body([], description='关联数据库'),  # noqa: B008
    dataset: Optional[str] = Body(DEFAULT_CHAT_DATASET, description='数据库名称'),  # noqa: B008
    priority: Optional[int] = Body(None, description='请求优先级，用于vllm调度。数值越大优先级越高'),  # noqa: B008
    prompt_template: Optional[str] = Body(
        None,
        description='追加到系统提示词的模板文本',
    ),  # noqa: B008
    available_tools: Optional[List[str]] = Body(
        ['all'],
        description='可用工具列表',
    ),  # noqa: B008
    available_skills: Optional[List[str]] = Body(
        ['all'],
        description='可用技能列表',
    ),  # noqa: B008
    skill_fs_url: Optional[str] = Body(
        None,
        description='远端 skill 文件系统 URL',
    ),  # noqa: B008
    memory: Optional[str] = Body(
        None,
        description='memory 内容',
    ),  # noqa: B008
    user_preference: Optional[str] = Body(
        None,
        description='user_preference 内容',
    ),  # noqa: B008
    use_memory: Optional[bool] = Body(
        True,
        description='是否使用 memory',
    ),  # noqa: B008
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
        prompt_template=prompt_template,
        available_tools=available_tools,
        available_skills=available_skills,
        skill_fs_url=skill_fs_url,
        memory=memory,
        user_preference=user_preference,
        use_memory=use_memory,
        is_stream=is_stream,
    )
