from types import SimpleNamespace

import chat.pipelines.builders.get_models as get_models_mod


def test_streaming_llm_module_forward_non_stream_trims_files(monkeypatch):
    seen = {}

    class _FakeBaseModel:
        _model_name = 'demo-model'

        def share(self, **kwargs):
            seen['share_kwargs'] = kwargs

            def _runner(query, stream_output, llm_chat_history, lazyllm_files, **kw):
                seen['runner'] = {
                    'query': query,
                    'stream_output': stream_output,
                    'history': llm_chat_history,
                    'files': lazyllm_files,
                    'kw': kw,
                }
                return 'ok'

            return _runner

    wrapper = get_models_mod._StreamingLlmModule(_FakeBaseModel())

    result = wrapper.forward(
        'hello',
        files=['a', 'b', 'c'],
        stream=False,
        llm_chat_history=[['u', 'a']],
        priority=3,
    )

    assert result == 'ok'
    assert seen['share_kwargs'] == {}
    assert seen['runner'] == {
        'query': 'hello',
        'stream_output': False,
        'history': [['u', 'a']],
        'files': ['a', 'b'],
        'kw': {
            'temperature': 0.01,
            'max_tokens': 4096,
            'frequency_penalty': 0,
            'priority': 3,
        },
    }


def test_get_automodel_caches_base_and_wrapped_models(monkeypatch):
    get_models_mod._base_models.clear()
    get_models_mod._wrapped_models.clear()

    monkeypatch.setattr(
        get_models_mod,
        'get_role_config',
        lambda role: ('demo-model', {'source': 'mock'}),
    )
    monkeypatch.setattr(
        get_models_mod,
        '_build_auto_model',
        lambda model, config: SimpleNamespace(name=model, config=config),
    )

    base1 = get_models_mod.get_automodel('llm')
    base2 = get_models_mod.get_automodel('llm')
    wrapped1 = get_models_mod.get_automodel('llm', wrap_simple_llm=True)
    wrapped2 = get_models_mod.get_automodel('llm', wrap_simple_llm=True)

    assert base1 is base2
    assert wrapped1 is wrapped2
    assert wrapped1.llm is base1
