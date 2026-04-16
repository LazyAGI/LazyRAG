from types import SimpleNamespace

import chat.pipelines.naive as naive_mod


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyPipe:
    def __init__(self, value=None):
        self.value = value

    def __or__(self, other):
        return self


class _DummyContextWithValue:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePipeline:
    def __init__(self, input_value):
        object.__setattr__(self, 'assignments', [])
        object.__setattr__(self, 'input', input_value)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name not in {'assignments', 'input'}:
            self.assignments.append(name)


def _capture(module, name, value):
    setattr(module, name, value)
    return value


def test_get_ppl_naive_uses_default_retriever_configs(monkeypatch):
    fake_rag_pipeline = _FakePipeline(
        {
            'priority': 1,
            'image_files': [],
            'files': [],
            'query': 'q',
            'history': [],
            'debug': False,
        }
    )
    fake_generate = _DummyPipe()
    expected_configs = [{'group_name': 'line', 'topk': 9}]

    monkeypatch.setattr(naive_mod.lazyllm, 'save_pipeline_result', lambda: _DummyContext())
    monkeypatch.setattr(naive_mod, 'pipeline', lambda: _DummyContextWithValue(fake_rag_pipeline))
    monkeypatch.setattr(naive_mod, 'ifs', lambda *args, **kwargs: 'rewriter')
    monkeypatch.setattr(naive_mod, 'bind', lambda **kwargs: _DummyPipe())
    monkeypatch.setattr(naive_mod, 'MultiturnQueryRewriter', lambda **kwargs: _DummyPipe())
    monkeypatch.setattr(naive_mod, 'get_automodel', lambda key: f'model:{key}')
    monkeypatch.setattr(
        naive_mod,
        'get_ppl_search',
        lambda url, retriever_configs: (
            _capture(naive_mod, 'search_args', (url, retriever_configs)),
            _DummyPipe('search'),
        )[1],
    )
    monkeypatch.setattr(naive_mod, 'get_ppl_generate', lambda stream=False: fake_generate)
    monkeypatch.setattr(
        naive_mod,
        'get_retrieval_settings',
        lambda: SimpleNamespace(retriever_configs=expected_configs),
    )

    result = naive_mod.get_ppl_naive('http://kb-service', retriever_configs=None, stream=True)

    assert result is fake_rag_pipeline
    assert getattr(naive_mod, 'search_args') == ('http://kb-service', expected_configs)


def test_get_ppl_naive_keeps_expected_stage_order(monkeypatch):
    fake_rag_pipeline = _FakePipeline(
        {
            'priority': 2,
            'image_files': ['img.png'],
            'files': [],
            'query': 'q',
            'history': ['turn-1'],
            'debug': True,
        }
    )
    recorded = {}

    monkeypatch.setattr(naive_mod.lazyllm, 'save_pipeline_result', lambda: _DummyContext())
    monkeypatch.setattr(naive_mod, 'pipeline', lambda: _DummyContextWithValue(fake_rag_pipeline))
    monkeypatch.setattr(naive_mod, 'bind', lambda **kwargs: ('bind', kwargs))
    monkeypatch.setattr(naive_mod, 'get_automodel', lambda key: f'model:{key}')
    monkeypatch.setattr(naive_mod, 'get_ppl_search', lambda url, retriever_configs: _DummyPipe('search'))
    monkeypatch.setattr(
        naive_mod,
        'get_ppl_generate',
        lambda stream=False: (
            recorded.__setitem__('stream', stream),
            _DummyPipe('generate'),
        )[1],
    )

    class _FakeRewriter(_DummyPipe):
        def __init__(self, **kwargs):
            super().__init__('rewriter')
            recorded['rewriter_init'] = kwargs

    monkeypatch.setattr(naive_mod, 'MultiturnQueryRewriter', _FakeRewriter)

    def _fake_ifs(cond, tpath, fpath):
        recorded['ifs'] = {'cond': cond, 'tpath': tpath, 'fpath': fpath}
        return 'rewriter-stage'

    monkeypatch.setattr(naive_mod, 'ifs', _fake_ifs)

    result = naive_mod.get_ppl_naive('http://kb-service', retriever_configs=[{'group_name': 'line'}], stream=True)

    assert result is fake_rag_pipeline
    assert fake_rag_pipeline.assignments == ['rewriter', 'search', 'generate']
    assert recorded['rewriter_init'] == {'llm': 'model:llm_instruct'}
    assert recorded['ifs']['fpath']('x') == 'x'
    assert recorded['stream'] is True
