import textwrap
from pathlib import Path

import pytest
import yaml

from common.model import build_model, get_model, get_runtime_model_settings, load_runtime_model_config
import common.model.utils as model_utils


@pytest.fixture(autouse=True)
def clear_runtime_model_cache():
    get_runtime_model_settings.cache_clear()
    yield
    get_runtime_model_settings.cache_clear()


def write_config(tmp_path, content: str):
    config_path = tmp_path / 'runtime_models.yaml'
    config_path.write_text(textwrap.dedent(content), encoding='utf-8')
    return config_path


def test_runtime_model_config_resolves_env_and_single_embed(monkeypatch, tmp_path):
    config_path = write_config(
        tmp_path,
        """
        llm:
          source: siliconflow
          type: llm
          model: foo-chat
          api_key: ${TEST_API_KEY}
        reranker:
          source: siliconflow
          type: rerank
          model: foo-rerank
          api_key: ${TEST_API_KEY}
        embeddings:
          embed_1:
            source: siliconflow
            type: embed
            model: foo-embed
            api_key: ${TEST_API_KEY}
        """,
    )
    monkeypatch.setenv('TEST_API_KEY', 'secret-key')

    config = load_runtime_model_config(str(config_path))
    settings = get_runtime_model_settings(str(config_path))

    assert config['llm']['api_key'] == 'secret-key'
    assert settings.embed_keys == ['embed_1']
    assert settings.temp_doc_embed_key == 'embed_1'
    assert settings.file_search_embed_key == 'embed_1'
    assert [item['embed_key'] for item in settings.index_kwargs] == ['embed_1']
    assert settings.retriever_configs == [
        {'group_name': 'line', 'embed_keys': ['embed_1'], 'topk': 20, 'target': 'block'},
        {'group_name': 'block', 'embed_keys': ['embed_1'], 'topk': 20},
    ]


def test_runtime_model_config_supports_multiple_embeds(monkeypatch, tmp_path):
    config_path = write_config(
        tmp_path,
        """
        llm:
          source: siliconflow
          type: llm
          model: foo-chat
          api_key: ${TEST_API_KEY}
        reranker:
          source: siliconflow
          type: rerank
          model: foo-rerank
          api_key: ${TEST_API_KEY}
        embeddings:
          embed_1:
            source: siliconflow
            type: embed
            model: dense-model
            api_key: ${TEST_API_KEY}
          embed_2:
            source: siliconflow
            type: embed
            model: sparse-model
            api_key: ${TEST_API_KEY}
            index_kwargs:
              index_type: SPARSE_INVERTED_INDEX
              metric_type: IP
        """,
    )
    monkeypatch.setenv('TEST_API_KEY', 'secret-key')

    settings = get_runtime_model_settings(str(config_path))

    assert settings.embed_keys == ['embed_1', 'embed_2']
    assert settings.file_search_embed_key == 'embed_2'
    assert [item['embed_key'] for item in settings.index_kwargs] == ['embed_1', 'embed_2']
    assert settings.retriever_configs[0]['embed_keys'] == ['embed_1']
    assert settings.retriever_configs[1]['embed_keys'] == ['embed_2']


def test_runtime_model_config_rejects_unknown_retrieval_embed_key(monkeypatch, tmp_path):
    config_path = write_config(
        tmp_path,
        """
        llm:
          source: siliconflow
          type: llm
          model: foo-chat
          api_key: ${TEST_API_KEY}
        reranker:
          source: siliconflow
          type: rerank
          model: foo-rerank
          api_key: ${TEST_API_KEY}
        embeddings:
          embed_1:
            source: siliconflow
            type: embed
            model: foo-embed
            api_key: ${TEST_API_KEY}
        retrieval:
          file_search_embed_key: embed_2
        """,
    )
    monkeypatch.setenv('TEST_API_KEY', 'secret-key')

    with pytest.raises(ValueError, match='unknown embed key'):
        get_runtime_model_settings(str(config_path))


def test_runtime_model_config_requires_env_when_placeholder_has_no_default(tmp_path):
    config_path = write_config(
        tmp_path,
        """
        llm:
          source: siliconflow
          type: llm
          model: foo-chat
          api_key: ${TEST_API_KEY}
        reranker:
          source: siliconflow
          type: rerank
          model: foo-rerank
          api_key: ${TEST_API_KEY}
        embeddings:
          embed_1:
            source: siliconflow
            type: embed
            model: foo-embed
            api_key: ${TEST_API_KEY}
        """,
    )

    with pytest.raises(ValueError, match='TEST_API_KEY'):
        load_runtime_model_config(str(config_path))


def test_runtime_model_settings_uses_default_runtime_config_path(monkeypatch, tmp_path):
    config_path = write_config(
        tmp_path,
        """
        llm:
          source: siliconflow
          type: llm
          model: foo-chat
          api_key: ${TEST_API_KEY}
        reranker:
          source: siliconflow
          type: rerank
          model: foo-rerank
          api_key: ${TEST_API_KEY}
        embeddings:
          embed_1:
            source: siliconflow
            type: embed
            model: foo-embed
            api_key: ${TEST_API_KEY}
        """,
    )
    monkeypatch.setenv('TEST_API_KEY', 'secret-key')
    monkeypatch.setenv('LAZYRAG_MODEL_CONFIG_PATH', str(config_path))

    settings = get_runtime_model_settings()

    assert settings.embed_keys == ['embed_1']
    assert settings.llm['model'] == 'foo-chat'


def test_build_model_uses_automodel_config_path_for_runtime_entry(monkeypatch):
    captured = {}

    def fake_auto_model(*, model, config, **kwargs):
        captured['model'] = model
        captured['config'] = config
        captured['kwargs'] = kwargs
        return 'fake-model'

    monkeypatch.setattr(model_utils, 'AutoModel', fake_auto_model)

    result = build_model({
        'source': 'bgem3embed',
        'type': 'embed',
        'model': 'bgem3_emb_dense_custom',
        'url': 'http://127.0.0.1:2269/embed',
        'skip_auth': True,
    })

    assert result == 'fake-model'
    assert captured['model'] == 'bgem3_emb_dense_custom'
    assert captured['kwargs'] == {}
    generated = yaml.safe_load(Path(captured['config']).read_text(encoding='utf-8'))
    assert generated == {
        'bgem3_emb_dense_custom': [{
            'source': 'bgem3embed',
            'type': 'embed',
            'model': 'bgem3_emb_dense_custom',
            'url': 'http://127.0.0.1:2269/embed',
            'skip_auth': True,
        }]
    }


def test_get_model_uses_automodel_config_path_for_inline_entry(monkeypatch):
    captured = {}

    def fake_auto_model(*, model, config, **kwargs):
        captured['model'] = model
        captured['config'] = config
        captured['kwargs'] = kwargs
        return 'fake-inline-model'

    monkeypatch.setattr(model_utils, 'AutoModel', fake_auto_model)

    result = get_model({
        'source': 'qwen3rerank',
        'type': 'rerank',
        'model': 'qwen3_reranker_custom',
        'url': 'http://127.0.0.1:8331/v1/rerank',
        'skip_auth': True,
    })

    assert result == 'fake-inline-model'
    assert captured['model'] == 'qwen3_reranker_custom'
    assert captured['kwargs'] == {}
    generated = yaml.safe_load(Path(captured['config']).read_text(encoding='utf-8'))
    assert generated == {
        'qwen3_reranker_custom': [{
            'source': 'qwen3rerank',
            'type': 'rerank',
            'model': 'qwen3_reranker_custom',
            'url': 'http://127.0.0.1:8331/v1/rerank',
            'skip_auth': True,
        }]
    }
