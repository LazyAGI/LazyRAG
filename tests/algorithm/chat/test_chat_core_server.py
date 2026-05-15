import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


def _import_chat_server_module(monkeypatch, *, default_dataset='algo', url_map=None):
    url_map = {'algo': 'http://kb-service,algo'} if url_map is None else url_map

    fake_lazyllm = ModuleType('lazyllm')
    fake_lazyllm.LOG = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    fake_lazyllm.once_wrapper = lambda fn: fn

    fake_config = ModuleType('chat.config')
    fake_config.URL_MAP = url_map
    fake_config.SENSITIVE_WORDS_PATH = '/tmp/sensitive.txt'
    fake_config.DEFAULT_CHAT_DATASET = default_dataset
    fake_config.resolve_dataset_url = lambda dataset: url_map.get(dataset)

    fake_agentic = ModuleType('chat.pipelines.agentic')
    fake_agentic.calls = []

    def fake_agentic_rag(params):
        fake_agentic.calls.append(params)
        return {'ok': True, 'params': params}

    fake_agentic.agentic_rag = fake_agentic_rag

    fake_filter_module = ModuleType('chat.components.process.sensitive_filter')

    class _FakeSensitiveFilter:
        def __init__(self, path):
            self.path = path
            self.loaded = True
            self.keyword_count = 2

    fake_filter_module.SensitiveFilter = _FakeSensitiveFilter

    for name in ['chat.app.core.chat_server', 'chat.app.api', 'chat.app.api.chat_routes', 'chat.app.api.health_routes']:
        sys.modules.pop(name, None)
    monkeypatch.setitem(sys.modules, 'lazyllm', fake_lazyllm)
    monkeypatch.setitem(sys.modules, 'chat.config', fake_config)
    monkeypatch.setitem(sys.modules, 'chat.pipelines.agentic', fake_agentic)
    monkeypatch.setitem(sys.modules, 'chat.components.process.sensitive_filter', fake_filter_module)

    module = importlib.import_module('chat.app.core.chat_server')
    return module, fake_agentic


def test_chat_server_builds_and_caches_pipelines(monkeypatch):
    module, fake_agentic = _import_chat_server_module(monkeypatch)
    server = module.ChatServer()

    assert server.startup_validated is True
    assert server.has_dataset('algo') is True
    assert server.has_dataset('missing') is False

    first = server.get_query_pipeline('algo')
    second = server.get_query_pipeline('algo')
    stream_pipeline = server.get_query_pipeline('algo', stream=True)
    first_result = first({'query': 'q'})
    stream_result = stream_pipeline({'query': 'q'})

    assert first is second
    assert callable(first)
    assert callable(stream_pipeline)
    assert first_result['ok'] is True
    assert stream_result['ok'] is True
    assert fake_agentic.calls == [
        {
            'query': 'q',
            'document_url': 'http://kb-service,algo',
            'stream': False,
        },
        {
            'query': 'q',
            'document_url': 'http://kb-service,algo',
            'stream': True,
        },
    ]


def test_chat_server_raises_when_default_dataset_missing(monkeypatch):
    with pytest.raises(KeyError, match='default dataset `missing` not found in URL_MAP'):
        _import_chat_server_module(
            monkeypatch,
            default_dataset='missing',
            url_map={'algo': 'http://kb-service,algo'},
        )
