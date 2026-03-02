import os
import asyncio
from typing import List, Optional, Dict, Any, TypeVar

from pydantic import BaseModel, Field
from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

import lazyllm
from lazyllm.tools.rag import Document
from lazyllm import LOG

app = FastAPI()
M = TypeVar("M")


class BaseResponse(BaseModel):
    code: int = Field(200, description="API status code")
    msg: str = Field("success", description="API status message")
    data: Optional[M] = Field(None, description="API data")

    class Config:
        schema_extra = {"example": {"code": 200, "msg": "success", "data": None}}


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


class History(BaseModel):
    role: str = Field("assistant", description="消息来自哪个角色，user / assistant")
    content: str = Field("", description="消息内容")


MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", 10))
rag_sem = asyncio.Semaphore(MAX_CONCURRENCY)


doc = Document(url=os.getenv('DOCUMENT_SERVER_URL', 'http://localhost:8000'))
llm = lazyllm.OnlineLLM().prompt('你是懒人RAG的助手，请根据用户的问题 `{query}` 和历史对话 `{history}` 以及参考文献 `{references}`，给出回答。')
r1 = lazyllm.Retriever(doc=doc, group_name="block", topk=25, embed_keys=["bge_m3_dense"], output_format='content', join='\n\n')


def ppl(query: str, history: List[History], filters: Optional[Dict[str, Any]], files: Optional[List[str]], debug: Optional[bool], reasoning: Optional[bool], databases: Optional[List[Dict]], priority: Optional[int]):
    refs = r1(query=query)
    return llm(dict(query=query, history=[h.dict() for h in history], references=refs))


@app.post("/api/chat", summary="与知识库对话")
@app.post("/api/chat/stream", summary="与知识库对话")
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
      int(os.getenv('LAZYRAG_LLM_PRIORITY', '0')),
      description="请求优先级，用于vllm调度。数值越大优先级越高，默认从环境变量LAZYRAG_LLM_PRIORITY读取")
) -> ChatResponse:
    cost = 0.0
    result = None
    try:
        import time
        t0 = time.perf_counter()
        async with rag_sem:
            lazyllm.globals._init_sid(sid=session_id)
            result = ppl(query=query, history=history, filters=filters, files=files, debug=debug, reasoning=reasoning, databases=databases, priority=priority)
        cost = time.perf_counter() - t0
        return ChatResponse(code=200, msg="success", data=result, cost=cost)
    except Exception as exc:
        LOG.exception(exc)
        return ChatResponse(code=500, msg=f"chat service failed: {exc}", cost=cost)



if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0", help="listen host")
    parser.add_argument("--port", type=int, default=8046, help="listen port")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
