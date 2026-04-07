from __future__ import annotations
from fastapi import FastAPI
from lazyllm import LOG, once_wrapper

from chat.utils.config import URL_MAP, SENSITIVE_WORDS_PATH
from chat.pipelines.agentic import agentic_rag
from chat.pipelines.naive import get_ppl_naive
from chat.components.process.sensitive_filter import SensitiveFilter


def create_app() -> FastAPI:
    """FastAPI 应用初始化与路由挂载；pipeline 在模块导入时由 ChatServer 注册。"""
    app = FastAPI(
        title='LazyLLM Chat API',
        description='基于知识库的对话 API 服务',
        version='1.0.0',
    )
    from chat.app.api import chat_routes, health_routes

    app.include_router(health_routes.router)
    app.include_router(chat_routes.router)
    return app


class ChatServer:
    def __init__(self):
        self._on_server_start()

    @once_wrapper
    def _on_server_start(self):
        try:
            self.query_ppl = {
                name: get_ppl_naive(url=doc_url)
                for name, doc_url in URL_MAP.items()
            }
            self.query_ppl_stream = {
                name: get_ppl_naive(url=doc_url, stream=True)
                for name, doc_url in URL_MAP.items()
            }
            self.query_ppl_reasoning = agentic_rag
            self.sensitive_filter = SensitiveFilter(SENSITIVE_WORDS_PATH)

            if self.sensitive_filter.loaded:
                LOG.info(
                    f'[ChatServer] [SENSITIVE_FILTER] Successfully loaded '
                    f'{self.sensitive_filter.keyword_count} sensitive keywords'
                )
            else:
                LOG.warning('[ChatServer] [SENSITIVE_FILTER] Failed to load, filter disabled')

            LOG.info('[ChatServer] [SERVER_START]')
        except Exception as exc:
            LOG.exception('[ChatServer] [SERVER_START_ERROR]')
            raise exc


chat_server = ChatServer()
