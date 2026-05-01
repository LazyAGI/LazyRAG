from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import FastAPI
from lazyllm import LOG, once_wrapper

from chat.config import URL_MAP, SENSITIVE_WORDS_PATH, DEFAULT_CHAT_DATASET
from chat.pipelines.agentic import agentic_rag
from chat.pipelines.naive import get_ppl_naive
from chat.components.process.sensitive_filter import SensitiveFilter


def create_app() -> FastAPI:
    """Initialize FastAPI app and mount routes; pipelines are registered by ChatServer on module import."""
    app = FastAPI(
        title='LazyLLM Chat API',
        description='Knowledge-base-backed conversational API service',
        version='1.0.0',
    )
    from chat.app.api import (
        chat_routes,
        health_routes,
        memory_generate_routes,
        model_check_routes,
        vocab_routes,
    )

    app.include_router(health_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(memory_generate_routes.router)
    app.include_router(model_check_routes.router)
    app.include_router(vocab_routes.router)
    return app


class ChatServer:
    def __init__(self):
        self.startup_validated = False
        self.startup_validation_error: Optional[str] = None
        self._on_server_start()

    @once_wrapper
    def _on_server_start(self):
        try:
            self.query_ppl: Dict[str, Any] = {}
            self.query_ppl_stream: Dict[str, Any] = {}
            self.query_ppl_reasoning = agentic_rag
            self.sensitive_filter = SensitiveFilter(SENSITIVE_WORDS_PATH)

            if self.sensitive_filter.loaded:
                LOG.info(
                    f'[ChatServer] [SENSITIVE_FILTER] Successfully loaded '
                    f'{self.sensitive_filter.keyword_count} sensitive keywords'
                )
            else:
                LOG.warning('[ChatServer] [SENSITIVE_FILTER] Failed to load, filter disabled')

            if DEFAULT_CHAT_DATASET in URL_MAP:
                self.get_query_pipeline(DEFAULT_CHAT_DATASET)
                self.get_query_pipeline(DEFAULT_CHAT_DATASET, stream=True)
                self.startup_validated = True
            else:
                self.startup_validation_error = (
                    f'default dataset `{DEFAULT_CHAT_DATASET}` not found in URL_MAP'
                )
                raise KeyError(self.startup_validation_error)

            LOG.info('[ChatServer] [SERVER_START]')
        except Exception as exc:
            self.startup_validated = False
            self.startup_validation_error = str(exc)
            LOG.exception('[ChatServer] [SERVER_START_ERROR]')
            raise exc

    def has_dataset(self, dataset: str) -> bool:
        return dataset in URL_MAP

    def get_query_pipeline(self, dataset: str, *, stream: bool = False) -> Any:
        if dataset not in URL_MAP:
            raise KeyError(f'dataset `{dataset}` not found in URL_MAP')
        pipeline_map = self.query_ppl_stream if stream else self.query_ppl
        if dataset not in pipeline_map:
            pipeline_map[dataset] = get_ppl_naive(url=URL_MAP[dataset], stream=stream)
        return pipeline_map[dataset]


chat_server = ChatServer()
