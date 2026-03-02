"""LazyLLM Knowledge‑Base Chat API
"""
from __future__ import annotations
import os
import sys
import time
import json
import uuid
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypeVar
from dotenv import load_dotenv
from fastapi import (
    Body,
    FastAPI,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import lazyllm
from lazyllm import LOG, once_wrapper

# ---------------------------------------------------------------------------
# 环境初始化
# ---------------------------------------------------------------------------
load_dotenv()

__dir__ = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.extend([p.as_posix() for p in Path(__dir__).parents])

from lazyrag.pipeline.agentic_rag_workflow import agentic_rag
from lazyrag.pipeline.query_pipeline_store import agentic_rag_ppl
from lazyrag.component.tools.sensitive_filter import SensitiveFilter

# ---------------------------------------------------------------------------
# 配置项与依赖注入
# ---------------------------------------------------------------------------
MOUNT_BASE_DIR: str = os.getenv("LAZYLLM_MOUNT_DIR", "/data")
SENSITIVE_WORDS_PATH: str = os.getenv("SENSITIVE_WORDS_PATH", "/lazyrag/data/sensitive_words.txt")
_LAZYRAG_LLM_PRIORITY_ENV = os.getenv("LAZYRAG_LLM_PRIORITY")
LAZYRAG_LLM_PRIORITY = int(_LAZYRAG_LLM_PRIORITY_ENV) if _LAZYRAG_LLM_PRIORITY_ENV is not None and _LAZYRAG_LLM_PRIORITY_ENV.isdigit() else 0

# 配置不同模式的开关
RAG_MODE = os.getenv("RAG_MODE", "True").lower() == "true"
MULTIMODAL_MODE = os.getenv("MULTIMODAL_MODE", "True").lower() == "true"

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------
# 敏感词被拦截时的响应文本
SENSITIVE_FILTER_RESPONSE_TEXT = "对不起，我还没有学会回答这个问题。如果你有其他问题，我非常乐意为你提供帮助。"
# 支持的图片扩展名
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

# ---------------------------------------------------------------------------
# 依赖的查询管线（sync / stream）
# ---------------------------------------------------------------------------
document_url = os.getenv("LAZYLLM_DOCUMENT_URL", "http://lazy-doc-agent:8525")
query_ppl = agentic_rag_ppl(url=document_url)
query_ppl_stream = agentic_rag_ppl(url=document_url, stream=True)

# ---------------------------------------------------------------------------
# Pydantic 响应模型
# ---------------------------------------------------------------------------
M = TypeVar("M")


class BaseResponse(BaseModel):
    code: int = Field(200, description="API status code")
    msg: str = Field("success", description="API status message")
    data: Optional[M] = Field(None, description="API data")

    class Config:
        schema_extra = {"example": {"code": 200, "msg": "success", "data": None}}


class History(BaseModel):
    role: str = Field("assistant", description="消息来自哪个角色，user / assistant")
    content: str = Field("", description="消息内容")


class ChatResponse(BaseResponse):
    cost: float = Field(0.0, description="API cost time (seconds)")

    class Config:
        schema_extra = {
            "example": {
                "code": 200,
                "msg": "success",
                "data": None,
                "cost": 0.1,
            }
        }


# ---------------------------------------------------------------------------
# FastAPI 实例
# ---------------------------------------------------------------------------
app = FastAPI(
    title="LazyLLM Chat API",
    description="基于知识库的对话 API 服务",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Server 封装
# ---------------------------------------------------------------------------
class ChatServer:
    def __init__(self):
        self._on_server_start()

    @once_wrapper
    def _on_server_start(self):
        try:
            self.query_ppl = query_ppl
            self.query_ppl_stream = query_ppl_stream
            self.query_ppl_reasoning = agentic_rag
            self.sensitive_filter = SensitiveFilter(SENSITIVE_WORDS_PATH)
            if self.sensitive_filter.loaded:
                LOG.info(
                    f"[ChatServer] [SENSITIVE_FILTER] Successfully loaded "
                    f"{self.sensitive_filter.keyword_count} sensitive keywords"
                )
            else:
                LOG.warning("[ChatServer] [SENSITIVE_FILTER] Failed to load, filter disabled")

            LOG.info("[ChatServer] [SERVER_START]")
        except Exception as exc:
            LOG.exception("[ChatServer] [SERVER_START_ERROR]")
            raise exc


chat_server = ChatServer()
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", 10))
rag_sem = asyncio.Semaphore(MAX_CONCURRENCY)

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _validate_and_resolve_files(files: Optional[List[str]]) -> tuple[List[str], List[str]]:
    """检查文件合法性并区分图片/非图片文件。"""
    if not files:
        return [], []

    resolved: List[str] = []
    for f in files:
        real_path = f if os.path.isabs(f) else os.path.join(MOUNT_BASE_DIR, f)
        if not (os.path.isfile(real_path) and os.access(real_path, os.R_OK)):
            raise HTTPException(status_code=400, detail=f"File {real_path} is not accessible")
        resolved.append(real_path)

    image_files = [p for p in resolved if p.lower().endswith(IMAGE_EXTENSIONS)]
    other_files = [p for p in resolved if p not in image_files]
    return other_files, image_files


def _check_sensitive_content(query: str, session_id: str, start_time: float) -> Optional[Tuple[float, str]]:
    """检查查询内容是否包含敏感词。"""
    if not chat_server.sensitive_filter.loaded:
        return None
    has_sensitive, sensitive_word = chat_server.sensitive_filter.check(query)
    if has_sensitive:
        cost = round(time.time() - start_time, 3)
        LOG.warning(
            f"[ChatServer] [SENSITIVE_FILTER_BLOCKED] [query={query[:50]}...] "
            f"[sensitive_word={sensitive_word}] [session_id={session_id}]"
        )
        return ChatResponse(
            code=200,
            msg="success",
            data={
                "think": None,
                "text": SENSITIVE_FILTER_RESPONSE_TEXT,
                "sources": []
            },
            cost=cost
        )
    return None

def _build_query_params(
    query: str,
    history: List[History],
    filters: Optional[Dict[str, Any]],
    other_files: List[str],
    image_files: List[str],
    debug: bool,
    databases: Optional[List[Dict[str, Any]]],
    priority: Optional[int]
) -> Dict[str, Any]:
    """构建查询参数"""
    return {
        "query": query,
        "history": [h.model_dump() for h in history],
        "filters": filters if RAG_MODE and filters else {},
        "files": other_files,
        "image_files": image_files if MULTIMODAL_MODE and image_files else [],
        "debug": debug,
        "databases": databases if RAG_MODE and databases else [],
        "priority": priority
    }


def _should_use_reasoning(reasoning: bool, query_params: Dict[str, Any]) -> bool:
    """判断是否应该使用推理模式"""
    return reasoning and (query_params.get("filters", {}).get("kb_id") or query_params.get("files"))


def _log_chat_request(
    query: str,
    session_id: str,
    filters: Optional[Dict[str, Any]],
    other_files: List[str],
    image_files: List[str],
    databases: Optional[List[Dict[str, Any]]],
    cost: float,
    response: Any = None,
    log_type: str = "KB_CHAT"
) -> None:
    """记录聊天请求日志"""
    databases_str = json.dumps(databases, ensure_ascii=False) if databases else []
    response_str = response if response is not None else None
    LOG.info(
        f"[ChatServer] [{log_type}] [query={query}] [session_id={session_id}] "
        f"[filters={filters}] [files={other_files}] [image_files={image_files}] "
        f"[databases={databases_str}] [cost={cost}] [response={response_str}]"
    )


# ---------------------------------------------------------------------------
# 非流式对话接口
# ---------------------------------------------------------------------------
@app.post("/api/chat", summary="与知识库对话")
async def chat(
    query: str = Body(..., description="用户问题"),
    history: List[History] = Body(default_factory=list, description="历史对话"),
    session_id: str = Body("session_id", description="会话 ID"),
    filters: Optional[Dict[str, Any]] = Body(None, description="检索过滤条件"),
    files: Optional[List[str]] = Body(None, description="上传临时文件"),
    debug: Optional[bool] = Body(False, description="是否开启debug模式"),
    reasoning: Optional[bool] = Body(False, description="是否开启推理"),
    databases: Optional[List[Dict]] = Body([], description="关联数据库"),
    priority: Optional[int] = Body(
      LAZYRAG_LLM_PRIORITY,
      description="请求优先级，用于vllm调度。数值越大优先级越高，默认从环境变量LAZYRAG_LLM_PRIORITY读取")
) -> ChatResponse:
    start_time = time.time()
    sid = f"{session_id}_{time.time()}_{uuid.uuid4().hex}"
    LOG.info(f"[ChatServer] [KB_CHAT] [query={query}] [sid={sid}]")

    # 敏感词检查
    sensitive_check_result = _check_sensitive_content(query, session_id, start_time)
    if sensitive_check_result:
        return sensitive_check_result

    other_files, image_files = _validate_and_resolve_files(files)
    query_params = _build_query_params(
        query, history, filters, other_files, image_files, debug, databases, priority
    )

    result = None
    try:
        async with rag_sem:
            lazyllm.globals._init_sid(sid=sid)
            if _should_use_reasoning(reasoning, query_params):
                result = await asyncio.to_thread(chat_server.query_ppl_reasoning, query_params, None, False)
            else:
                result = await asyncio.to_thread(chat_server.query_ppl, query_params)
            cost = round(time.time() - start_time, 3)
            return ChatResponse(code=200, msg="success", data=result, cost=cost)
    except Exception as exc:
        LOG.exception(exc)
        cost = round(time.time() - start_time, 3)
        return ChatResponse(code=500, msg=f"chat service failed: {exc}", cost=cost)
    finally:
        cost = round(time.time() - start_time, 3)
        _log_chat_request(query, sid, filters, other_files, image_files, databases, cost, result)


# ---------------------------------------------------------------------------
# 流式对话接口 (SSE)
# ---------------------------------------------------------------------------
@app.post("/api/chat_stream", summary="与知识库对话(流式)")
async def chat_stream(
    query: str = Body(..., description="用户问题"),
    history: List[History] = Body(default_factory=list, description="历史对话"),
    session_id: str = Body("session_id", description="会话 ID"),
    filters: Optional[Dict[str, Any]] = Body(None, description="检索过滤条件"),
    files: Optional[List[str]] = Body(None, description="上传临时文件"),
    reasoning: Optional[bool] = Body(False, description="是否开启推理"),
    databases: Optional[List[Dict]] = Body(None, description="关联数据库"),
    priority: Optional[int] = Body(
      LAZYRAG_LLM_PRIORITY,
      description="请求优先级，用于vllm调度。数值越大优先级越高，默认从环境变量LAZYRAG_LLM_PRIORITY读取")
) -> StreamingResponse:
    start_time = time.time()
    first_frame_logged = False  # 标记是否已记录首帧耗时
    sid = f"{session_id}_{time.time()}_{uuid.uuid4().hex}"
    LOG.info(f"[ChatServer] [KB_CHAT_STREAM] [query={query}] [sid={sid}]")

    # 敏感词检查
    sensitive_check_result = _check_sensitive_content(query, session_id, start_time)
    if sensitive_check_result:
        async def error_stream():
            yield sensitive_check_result.model_dump_json() + "\n\n"
            finish_resp = ChatResponse(code=200, msg="success", data={"status": "FINISHED"})
            yield finish_resp.model_dump_json() + "\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    other_files, image_files = _validate_and_resolve_files(files)
    collected_chunks: List[str] = []

    query_params = _build_query_params(
        query, history, filters, other_files, image_files, False, databases, priority
    )

    async def event_stream(ppl, *args, **kwargs) -> Any:
        nonlocal first_frame_logged
        try:
            async with rag_sem:
                lazyllm.globals._init_sid(sid=sid)
                async_result = await asyncio.to_thread(ppl, *args, **kwargs)
                async for chunk in async_result:
                    now = time.time()
                    # ------ 记录首帧耗时 ----------------------------------
                    if not first_frame_logged:
                        first_cost = round(now - start_time, 3)
                        LOG.info(
                            f"[ChatServer] [KB_CHAT_STREAM_FIRST_FRAME] "
                            f"[query={query}] [session_id={session_id}] "
                            f"[cost={first_cost}]"
                        )
                        first_frame_logged = True
                    # ---------------------------------------------------------

                    chunk_str = chunk if isinstance(chunk, str) else json.dumps(chunk, ensure_ascii=False)
                    collected_chunks.append(chunk_str)
                    cost = round(now - start_time, 3)
                    yield ChatResponse(code=200, msg="success", data=chunk, cost=cost).model_dump_json() + "\n\n"

        except Exception as exc:
            LOG.exception(exc)
            collected_chunks.append(f"[EXCEPTION]: {str(exc)}")
            final_resp = ChatResponse(code=500, msg=f"chat service failed: {exc}", data={"status": "FAILED"})
        else:
            final_resp = ChatResponse(code=200, msg="success", data={"status": "FINISHED"})

        cost = round(time.time() - start_time, 3)
        final_resp.cost = cost
        yield final_resp.model_dump_json() + "\n\n"

        response_text = "\n".join(collected_chunks)
        _log_chat_request(query, sid, filters, other_files, image_files, databases, cost, response_text, "KB_CHAT_STREAM_FINISH")

    if _should_use_reasoning(reasoning, query_params):
        return StreamingResponse(event_stream(chat_server.query_ppl_reasoning, query_params, None, True), media_type="text/event-stream")
    return StreamingResponse(event_stream(chat_server.query_ppl_stream, query_params), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 应用启动 (本地调试)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0", help="listen host")
    parser.add_argument("--port", type=int, default=8046, help="listen port")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
