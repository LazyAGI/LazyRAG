"""Tests for dynamic model config: AutoModel dynamic shortcut, astream_call,
_inject_model_config, session isolation, and API parameter forwarding."""
import asyncio
import importlib
import sys
import textwrap
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / 'runtime_models.yaml'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# Task 1: AutoModel source=dynamic shortcut
# ---------------------------------------------------------------------------

class TestAutoModelDynamic:
    def test_dynamic_source_returns_online_chat_module(self):
        '''AutoModel(source="dynamic") should return an OnlineChatModule instance.'''
        from lazyllm import AutoModel
        from lazyllm.module.llms.onlinemodule.chat import OnlineChatModule

        module = AutoModel(source='dynamic')
        assert isinstance(module, OnlineChatModule)

    def test_dynamic_source_with_dynamic_auth(self):
        '''dynamic_auth=True should be forwarded to OnlineChatModule.'''
        from lazyllm import AutoModel
        from lazyllm.module.llms.onlinemodule.chat import OnlineChatModule

        module = AutoModel(source='dynamic', dynamic_auth=True)
        assert isinstance(module, OnlineChatModule)
        # _api_key is set to 'dynamic' when dynamic_auth=True
        assert module._api_key == 'dynamic'

    def test_dynamic_source_from_yaml_config(self, tmp_path):
        '''AutoModel(model="llm", config=path) with source=dynamic in yaml should return OnlineChatModule.'''
        from lazyllm import AutoModel
        from lazyllm.module.llms.onlinemodule.chat import OnlineChatModule

        config_path = write_yaml(tmp_path, """
            llm:
              source: dynamic
              dynamic_auth: true
              type: llm
        """)

        module = AutoModel(model='llm', config=str(config_path))
        assert isinstance(module, OnlineChatModule)


# ---------------------------------------------------------------------------
# Task 2: StreamCallHelper.astream
# ---------------------------------------------------------------------------

class TestStreamCallHelperAstream:
    def test_astream_yields_chunks(self):
        '''StreamCallHelper.astream should yield tokens from FileSystemQueue.'''
        import lazyllm
        from lazyllm.tools.common import StreamCallHelper

        chunks_received = []

        def fake_impl(*args, **kwargs):
            # Simulate writing to the queue
            lazyllm.FileSystemQueue().enqueue(['hello', ' world'])
            return 'hello world'

        helper = StreamCallHelper(fake_impl, interval=0.01)

        async def run():
            async for chunk in helper.astream('input'):
                chunks_received.append(chunk)

        asyncio.run(run())
        assert len(chunks_received) >= 1
        assert any('hello' in c for c in chunks_received)

    def test_astream_yields_result_when_queue_empty(self):
        '''When queue is empty, astream should still yield the final result.'''
        from lazyllm.tools.common import StreamCallHelper

        def fake_impl(*args, **kwargs):
            return 'final answer'

        helper = StreamCallHelper(fake_impl, interval=0.01)
        results = []

        async def run():
            async for chunk in helper.astream('input'):
                results.append(chunk)

        asyncio.run(run())
        assert 'final answer' in results


# ---------------------------------------------------------------------------
# Task 3: LLMBase.astream_call
# ---------------------------------------------------------------------------

class TestLLMBaseAstreamCall:
    def test_astream_call_is_async_generator(self):
        '''LLMBase.astream_call should be an async generator method.'''
        import inspect
        from lazyllm.module.servermodule import LLMBase

        assert inspect.isasyncgenfunction(LLMBase.astream_call)

    def test_astream_call_delegates_to_stream_call_helper(self):
        '''astream_call should yield chunks via StreamCallHelper.astream.'''
        from lazyllm.module.servermodule import LLMBase
        from lazyllm.tools.common import StreamCallHelper

        chunks = []
        fake_chunks = ['tok1', 'tok2']

        async def fake_astream(self_helper, *args, **kwargs):
            for c in fake_chunks:
                yield c

        with patch.object(StreamCallHelper, 'astream', fake_astream):
            # Create a minimal LLMBase-like object with share()
            class FakeLLM(LLMBase):
                def __init__(self):
                    # Skip full LLMBase init to avoid side effects
                    self._stream = False
                    self._type = None
                    self._static_params = {}
                    self._prompt = None
                    self._formatter = None

                def share(self, **kwargs):
                    return self

                def __call__(self, *args, **kwargs):
                    return 'result'

            llm = FakeLLM()

            async def run():
                async for chunk in llm.astream_call('query'):
                    chunks.append(chunk)

            asyncio.run(run())

        assert chunks == fake_chunks


# ---------------------------------------------------------------------------
# Task 4: _inject_model_config
# ---------------------------------------------------------------------------

def _load_chat_service(monkeypatch):
    '''Load chat_service with a minimal lazyllm stub.'''
    fake_globals_store: Dict[str, Any] = {}

    class FakeGlobalsConfig:
        def get(self, key, default=None):
            return fake_globals_store.get(key, default)

        def __getitem__(self, key):
            return fake_globals_store.get(key)

        def __setitem__(self, key, value):
            fake_globals_store[key] = value

    fake_lazyllm = ModuleType('lazyllm')
    fake_lazyllm.globals = SimpleNamespace(
        _init_sid=lambda sid=None: None,
        config=FakeGlobalsConfig(),
    )
    fake_lazyllm.locals = SimpleNamespace(_init_sid=lambda sid=None: None)
    fake_lazyllm.LOG = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        exception=lambda *a, **k: None,
    )

    monkeypatch.setitem(sys.modules, 'lazyllm', fake_lazyllm)
    sys.modules.pop('chat.app.core.chat_service', None)

    return importlib.import_module('chat.app.core.chat_service'), fake_globals_store


class TestInjectModelConfig:
    def test_writes_chat_bucket_to_globals(self, monkeypatch):
        '''_inject_model_config should write source/model/url/skip_auth to globals config.'''
        from lazyllm.module.llms.onlinemodule.dynamic_router import ConfigsDict
        from chat.app.core.chat_service import _inject_model_config
        import lazyllm

        # Patch globals to use a real ConfigsDict
        store: Dict[str, Any] = {}

        class _Cfg:
            def get(self, k, d=None): return store.get(k, d)
            def __getitem__(self, k): return store.get(k)
            def __setitem__(self, k, v): store[k] = v

        with patch.object(lazyllm.globals, 'config', _Cfg()):
            _inject_model_config({
                'source': 'openai',
                'name': 'gpt-4o',
                'base_url': 'https://api.openai.com/v1',
                'skip_auth': False,
            })

        cfg = store.get('dynamic_model_configs')
        assert cfg is not None
        assert cfg['chat']['source'] == 'openai'
        assert cfg['chat']['model'] == 'gpt-4o'
        assert cfg['chat']['url'] == 'https://api.openai.com/v1'

    def test_noop_on_none(self):
        '''_inject_model_config(None) should not touch globals.'''
        from chat.app.core.chat_service import _inject_model_config
        import lazyllm

        original = lazyllm.globals.config.get('dynamic_model_configs')
        _inject_model_config(None)
        assert lazyllm.globals.config.get('dynamic_model_configs') == original

    def test_noop_on_empty_dict(self):
        '''_inject_model_config({}) should not write anything.'''
        from chat.app.core.chat_service import _inject_model_config
        import lazyllm

        original = lazyllm.globals.config.get('dynamic_model_configs')
        _inject_model_config({})
        assert lazyllm.globals.config.get('dynamic_model_configs') == original

    def test_skips_none_fields(self):
        '''Only non-None fields should appear in the bucket.'''
        from lazyllm.module.llms.onlinemodule.dynamic_router import ConfigsDict
        from chat.app.core.chat_service import _inject_model_config
        import lazyllm

        store: Dict[str, Any] = {}

        class _Cfg:
            def get(self, k, d=None): return store.get(k, d)
            def __getitem__(self, k): return store.get(k)
            def __setitem__(self, k, v): store[k] = v

        with patch.object(lazyllm.globals, 'config', _Cfg()):
            _inject_model_config({'source': 'qwen', 'name': None, 'base_url': None})

        cfg = store.get('dynamic_model_configs')
        assert 'source' in cfg['chat']
        assert 'model' not in cfg['chat']
        assert 'url' not in cfg['chat']


# ---------------------------------------------------------------------------
# Task 5: chat_routes model_config parameter forwarding
# ---------------------------------------------------------------------------

def _load_chat_routes_module():
    module_name = 'test_chat_routes_isolated_dynamic'
    module_path = Path(__file__).resolve().parents[3] / 'algorithm/chat/app/api/chat_routes.py'
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestChatRouteModelConfig:
    def test_model_config_forwarded_to_handle_chat(self, monkeypatch):
        '''chat route should forward model_config to handle_chat.'''
        import importlib.util
        recorded = {}

        async def fake_handle_chat(**kwargs):
            recorded.update(kwargs)
            return {'ok': True}

        fake_service = ModuleType('chat.app.core.chat_service')
        fake_service.handle_chat = fake_handle_chat

        fake_config = ModuleType('chat.config')
        fake_config.DEFAULT_CHAT_DATASET = 'default'

        monkeypatch.setitem(sys.modules, 'chat.app.core.chat_service', fake_service)
        monkeypatch.setitem(sys.modules, 'chat.config', fake_config)

        routes_mod = _load_chat_routes_module()

        async def run():
            fake_request = SimpleNamespace(url=SimpleNamespace(path='/api/chat'))
            await routes_mod.chat(
                query='hello',
                session_id='sid-1',
                model_config={'source': 'openai', 'name': 'gpt-4o'},
                request=fake_request,
            )

        asyncio.run(run())
        assert recorded.get('model_config') == {'source': 'openai', 'name': 'gpt-4o'}

    def test_model_config_defaults_to_none(self, monkeypatch):
        '''model_config should default to None when not provided.'''
        import importlib.util
        recorded = {}

        async def fake_handle_chat(**kwargs):
            recorded.update(kwargs)
            return {'ok': True}

        fake_service = ModuleType('chat.app.core.chat_service')
        fake_service.handle_chat = fake_handle_chat

        fake_config = ModuleType('chat.config')
        fake_config.DEFAULT_CHAT_DATASET = 'default'

        monkeypatch.setitem(sys.modules, 'chat.app.core.chat_service', fake_service)
        monkeypatch.setitem(sys.modules, 'chat.config', fake_config)

        routes_mod = _load_chat_routes_module()

        async def run():
            fake_request = SimpleNamespace(url=SimpleNamespace(path='/api/chat'))
            await routes_mod.chat(query='hello', session_id='sid-1', request=fake_request)

        asyncio.run(run())
        assert recorded.get('model_config') is None
