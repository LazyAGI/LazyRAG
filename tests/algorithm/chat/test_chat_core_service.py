import asyncio
import importlib
import json
import sys
from types import ModuleType, SimpleNamespace


def _import_chat_service_module(monkeypatch, *, chat_server=None):
    fake_lazyllm = ModuleType('lazyllm')
    fake_lazyllm.LOG = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    fake_lazyllm.globals = SimpleNamespace(_init_sid=lambda sid: None)
    fake_lazyllm.locals = SimpleNamespace(_init_sid=lambda sid: None)

    fake_config = ModuleType('chat.config')
    fake_config.URL_MAP = {'algo': 'http://kb-service,algo'}
    fake_config.RAG_MODE = True
    fake_config.MULTIMODAL_MODE = True
    fake_config.MAX_CONCURRENCY = 2
    fake_config.LAZYRAG_LLM_PRIORITY = 5
    fake_config.SENSITIVE_FILTER_RESPONSE_TEXT = 'blocked'

    fake_helpers = ModuleType('chat.utils.helpers')
    fake_helpers.validate_and_resolve_files = lambda files: (['/tmp/a.txt'], ['/tmp/b.png'])

    if chat_server is None:
        chat_server = SimpleNamespace(
            sensitive_filter=SimpleNamespace(loaded=False, check=lambda query: (False, None)),
            has_dataset=lambda dataset: dataset == 'algo',
            get_query_pipeline=lambda dataset, stream=False: f'pipeline:{dataset}:{stream}',
            query_ppl_reasoning='reasoning-pipeline',
        )

    fake_server = ModuleType('chat.app.core.chat_server')
    fake_server.chat_server = chat_server

    sys.modules.pop('chat.app.core.chat_service', None)
    monkeypatch.setitem(sys.modules, 'lazyllm', fake_lazyllm)
    monkeypatch.setitem(sys.modules, 'chat.config', fake_config)
    monkeypatch.setitem(sys.modules, 'chat.utils.helpers', fake_helpers)
    monkeypatch.setitem(sys.modules, 'chat.app.core.chat_server', fake_server)

    return importlib.import_module('chat.app.core.chat_service')


def test_sse_line_and_resp_helpers(monkeypatch):
    module = _import_chat_service_module(monkeypatch)

    payload = module._resp(200, 'success', {'x': 1}, 0.25)

    assert payload == {'code': 200, 'msg': 'success', 'data': {'x': 1}, 'cost': 0.25}
    assert json.loads(module._sse_line(payload).strip()) == payload


def test_check_sensitive_content_returns_block_response(monkeypatch):
    chat_server = SimpleNamespace(
        sensitive_filter=SimpleNamespace(loaded=True, check=lambda query: (True, 'secret')),
    )
    module = _import_chat_service_module(monkeypatch, chat_server=chat_server)

    result = module.check_sensitive_content('secret question', 'sid-1', 0.0)

    assert result['code'] == 200
    assert result['msg'] == 'success'
    assert result['data']['text'] == 'blocked'
    assert result['data']['sources'] == []


def test_build_query_params_filters_history_and_modes(monkeypatch):
    module = _import_chat_service_module(monkeypatch)

    params = module.build_query_params(
        query='hello',
        history=[{'role': 'user', 'content': 123}, 'ignore-me', {'content': 'answer'}],
        filters={'scope': 'all'},
        other_files=['doc.txt'],
        databases=[{'name': 'db'}],
        debug=True,
        image_files=['img.png'],
        priority=8,
    )

    assert params == {
        'query': 'hello',
        'history': [
            {'role': 'user', 'content': '123'},
            {'role': 'assistant', 'content': 'answer'},
        ],
        'filters': {'scope': 'all'},
        'files': ['doc.txt'],
        'image_files': ['img.png'],
        'debug': True,
        'databases': [{'name': 'db'}],
        'priority': 8,
    }


def test_handle_chat_rejects_unknown_dataset(monkeypatch):
    chat_server = SimpleNamespace(
        sensitive_filter=SimpleNamespace(loaded=False, check=lambda query: (False, None)),
        has_dataset=lambda dataset: False,
    )
    module = _import_chat_service_module(monkeypatch, chat_server=chat_server)

    result = asyncio.run(
        module.handle_chat(
            query='hello',
            history=None,
            session_id='sid-1',
            filters=None,
            files=None,
            debug=False,
            reasoning=False,
            databases=None,
            dataset='missing',
            priority=None,
            is_stream=False,
        )
    )

    assert result == {'code': 400, 'msg': 'dataset missing not found', 'data': None, 'cost': 0.0}


def test_handle_chat_non_stream_returns_pipeline_result(monkeypatch):
    module = _import_chat_service_module(monkeypatch)

    async def fake_run_sync_ppl(reasoning, dataset, query_params, query, filters, priority):
        assert reasoning is False
        assert dataset == 'algo'
        assert query == 'hello'
        assert filters == {'scope': 'all'}
        assert priority == 5
        assert query_params['files'] == ['/tmp/a.txt']
        assert query_params['image_files'] == ['/tmp/b.png']
        return {'text': 'answer'}

    monkeypatch.setattr(module, '_run_sync_ppl', fake_run_sync_ppl)

    result = asyncio.run(
        module.handle_chat(
            query='hello',
            history=[],
            session_id='sid-1',
            filters={'scope': 'all'},
            files=['input.txt'],
            debug=False,
            reasoning=False,
            databases=[],
            dataset='algo',
            priority=None,
            is_stream=False,
        )
    )

    assert result['code'] == 200
    assert result['msg'] == 'success'
    assert result['data'] == {'text': 'answer'}


def test_run_sync_ppl_uses_reasoning_pipeline(monkeypatch):
    captured = {}

    def fake_reasoning(query_arg, kb_search, stream_flag):
        captured['query_arg'] = query_arg
        captured['kb_search'] = kb_search
        captured['stream_flag'] = stream_flag
        return {'text': 'reasoned'}

    chat_server = SimpleNamespace(
        sensitive_filter=SimpleNamespace(loaded=False, check=lambda query: (False, None)),
        has_dataset=lambda dataset: True,
        query_ppl_reasoning=fake_reasoning,
        get_query_pipeline=lambda dataset, stream=False: 'unused',
    )
    module = _import_chat_service_module(monkeypatch, chat_server=chat_server)

    async def fake_to_thread(fn, *args):
        return fn(*args)

    monkeypatch.setattr(module.asyncio, 'to_thread', fake_to_thread)

    result = asyncio.run(
        module._run_sync_ppl(
            True,
            'algo',
            {'query': 'ignored'},
            'hello',
            {'scope': 'all'},
            7,
        )
    )

    assert result == {'text': 'reasoned'}
    assert captured == {
        'query_arg': {'query': 'hello'},
        'kb_search': {
            'kb_search': {
                'filters': {'scope': 'all'},
                'files': [],
                'stream': False,
                'priority': 7,
                'document_url': 'http://kb-service,algo',
            }
        },
        'stream_flag': False,
    }
