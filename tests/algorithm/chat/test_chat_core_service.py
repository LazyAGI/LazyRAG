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


def _decode_sse_payloads(raw_chunks):
    payloads = []
    for raw in raw_chunks:
        for line in raw.splitlines():
            if line.strip():
                payloads.append(json.loads(line))
    return payloads


def test_handle_chat_stream_returns_sse_chunks_and_final_status(monkeypatch):
    first_frame_logs = []
    init_calls = []
    captured = {}

    async def _stream():
        yield {'text': 'chunk-1'}
        yield {'text': 'chunk-2'}

    def _pipeline(query_params):
        captured['query_params'] = query_params
        return _stream()

    chat_server = SimpleNamespace(
        sensitive_filter=SimpleNamespace(loaded=False, check=lambda query: (False, None)),
        has_dataset=lambda dataset: dataset == 'algo',
        get_query_pipeline=lambda dataset, stream=False: _pipeline,
        query_ppl_reasoning='unused',
    )
    module = _import_chat_service_module(monkeypatch, chat_server=chat_server)

    class _FakeStreamingResponse:
        def __init__(self, body_iterator, media_type):
            self.body_iterator = body_iterator
            self.media_type = media_type

    async def fake_to_thread(fn, *args):
        return fn(*args)

    monkeypatch.setattr(module, 'validate_and_resolve_files', lambda files: (['/tmp/a.txt'], ['/tmp/b.png']))
    monkeypatch.setattr(module.LOG, 'info', lambda message: first_frame_logs.append(message))
    monkeypatch.setattr(module.lazyllm.globals, '_init_sid', lambda sid: init_calls.append(('global', sid)))
    monkeypatch.setattr(module.lazyllm.locals, '_init_sid', lambda sid: init_calls.append(('local', sid)))
    monkeypatch.setattr(module, 'StreamingResponse', _FakeStreamingResponse)
    monkeypatch.setattr(module.asyncio, 'to_thread', fake_to_thread)

    response = asyncio.run(
        module.handle_chat(
            query='hello',
            history=[{'role': 'user', 'content': 'hi'}],
            session_id='sid-1',
            filters={'scope': 'all'},
            files=['doc.txt', 'img.png'],
            debug=True,
            reasoning=False,
            databases=[{'name': 'db'}],
            dataset='algo',
            priority=9,
            is_stream=True,
        )
    )

    async def _collect():
        return [chunk async for chunk in response.body_iterator]

    payloads = _decode_sse_payloads(asyncio.run(_collect()))

    assert captured['query_params'] == {
        'query': 'hello',
        'history': [{'role': 'user', 'content': 'hi'}],
        'filters': {'scope': 'all'},
        'files': ['/tmp/a.txt'],
        'image_files': ['/tmp/b.png'],
        'debug': False,
        'databases': [{'name': 'db'}],
        'priority': 9,
    }
    assert [payload['data'] for payload in payloads] == [
        {'text': 'chunk-1'},
        {'text': 'chunk-2'},
        {'status': 'FINISHED'},
    ]
    assert any('KB_CHAT_STREAM_FIRST_FRAME' in message for message in first_frame_logs)
    assert init_calls == [('global', 'sid-1'), ('local', 'sid-1')]


def test_handle_chat_concurrency_respects_semaphore_and_session_isolation(monkeypatch):
    init_calls = []
    start_order = []
    release_first = asyncio.Event()

    module = _import_chat_service_module(monkeypatch)
    monkeypatch.setattr(module, 'rag_sem', asyncio.Semaphore(1))
    monkeypatch.setattr(module, 'validate_and_resolve_files', lambda files: ([], []))
    monkeypatch.setattr(module.lazyllm.globals, '_init_sid', lambda sid: init_calls.append(('global', sid)))
    monkeypatch.setattr(module.lazyllm.locals, '_init_sid', lambda sid: init_calls.append(('local', sid)))

    async def fake_run_sync_ppl(reasoning, dataset, query_params, query, filters, priority):
        start_order.append(query)
        if query == 'q1':
            await release_first.wait()
        return {'text': query}

    monkeypatch.setattr(module, '_run_sync_ppl', fake_run_sync_ppl)

    async def _run_pair():
        task1 = asyncio.create_task(
            module.handle_chat(
                query='q1',
                history=[],
                session_id='sid-1',
                filters=None,
                files=None,
                debug=False,
                reasoning=False,
                databases=None,
                dataset='algo',
                priority=None,
                is_stream=False,
            )
        )
        await asyncio.sleep(0)
        task2 = asyncio.create_task(
            module.handle_chat(
                query='q2',
                history=[],
                session_id='sid-2',
                filters=None,
                files=None,
                debug=False,
                reasoning=False,
                databases=None,
                dataset='algo',
                priority=None,
                is_stream=False,
            )
        )
        await asyncio.sleep(0)
        assert start_order == ['q1']
        release_first.set()
        return await asyncio.gather(task1, task2)

    results = asyncio.run(_run_pair())

    assert [item['data'] for item in results] == [{'text': 'q1'}, {'text': 'q2'}]
    assert start_order == ['q1', 'q2']
    assert init_calls == [
        ('global', 'sid-1'),
        ('local', 'sid-1'),
        ('global', 'sid-2'),
        ('local', 'sid-2'),
    ]


def test_log_chat_request_includes_observability_fields(monkeypatch):
    messages = []
    module = _import_chat_service_module(monkeypatch)
    monkeypatch.setattr(module.LOG, 'info', lambda message: messages.append(message))

    module.log_chat_request(
        'hello',
        'sid-1',
        {'scope': 'all'},
        ['/tmp/a.txt'],
        [{'name': 'db'}],
        ['/tmp/b.png'],
        0.123,
        {'text': 'answer'},
        'KB_CHAT_STREAM_FINISH',
    )

    assert len(messages) == 1
    message = messages[0]
    assert '[KB_CHAT_STREAM_FINISH]' in message
    assert '[session_id=sid-1]' in message
    assert "[files=['/tmp/a.txt']]" in message
    assert "[image_files=['/tmp/b.png']]" in message
    assert '[cost=0.123]' in message
