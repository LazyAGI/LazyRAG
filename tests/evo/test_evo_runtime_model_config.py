import textwrap
from pathlib import Path

import pytest
import yaml

try:
    import lazyllm  # noqa: F401
except Exception as exc:
    pytest.skip(f'lazyllm unavailable in test environment: {exc}', allow_module_level=True)

from chat.utils.load_config import get_retrieval_settings, load_model_config

try:
    import chat.pipelines.builders.get_models as get_models_mod
except ImportError:
    get_models_mod = None


@pytest.fixture(autouse=True)
def clear_caches():
    get_retrieval_settings.cache_clear()
    yield
    get_retrieval_settings.cache_clear()


def write_config(tmp_path, content: str):
    config_path = tmp_path / 'runtime_models.yaml'
    config_path.write_text(textwrap.dedent(content), encoding='utf-8')
    return config_path


def test_model_config_resolves_env_and_single_embed(monkeypatch, tmp_path):
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

    config = load_model_config(str(config_path), expand_env=True)
    settings = get_retrieval_settings(str(config_path))

    assert config['llm']['api_key'] == 'secret-key'
    assert settings.embed_keys == ['embed_1']
    assert settings.temp_doc_embed_key == 'embed_1'
    assert settings.file_search_embed_key == 'embed_1'
    assert [item['embed_key'] for item in settings.index_kwargs] == ['embed_1']
    assert settings.retriever_configs == [
        {'group_name': 'line', 'embed_keys': ['embed_1'], 'topk': 20, 'target': 'block'},
        {'group_name': 'block', 'embed_keys': ['embed_1'], 'topk': 20},
    ]


def test_model_config_supports_multiple_embeds(monkeypatch, tmp_path):
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

    settings = get_retrieval_settings(str(config_path))

    assert settings.embed_keys == ['embed_1', 'embed_2']
    assert settings.file_search_embed_key == 'embed_2'
    assert [item['embed_key'] for item in settings.index_kwargs] == ['embed_1', 'embed_2']
    assert settings.retriever_configs[0]['embed_keys'] == ['embed_1']
    assert settings.retriever_configs[1]['embed_keys'] == ['embed_2']


def test_model_config_rejects_unknown_retrieval_embed_key(monkeypatch, tmp_path):
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

    with pytest.raises(ValueError, match='embed_2'):
        get_retrieval_settings(str(config_path))


def test_model_config_requires_env_when_placeholder_has_no_default(tmp_path):
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
        load_model_config(str(config_path), expand_env=True)


def test_model_config_uses_env_override_path(monkeypatch, tmp_path):
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

    config = load_model_config(expand_env=True)
    settings = get_retrieval_settings()

    assert config['llm']['model'] == 'foo-chat'
    assert settings.embed_keys == ['embed_1']


@pytest.mark.skipif(get_models_mod is None,
                    reason="chat.pipelines.builders.get_models module has been removed")
def test_build_auto_model_writes_config_file(monkeypatch, tmp_path):
    captured = {}

    def fake_auto_model(*, model, config, **kwargs):
        captured['model'] = model
        captured['config'] = config
        return 'fake-model'

    monkeypatch.setattr(get_models_mod, 'AutoModel', fake_auto_model)
    monkeypatch.setattr(get_models_mod, '_RUNTIME_AUTO_MODEL_DIR', tmp_path / 'runtime-auto-model')

    result = get_models_mod._build_auto_model('BAAI/bge-reranker-v2-m3', {
        'source': 'siliconflow',
        'type': 'rerank',
        'api_key': 'secret-key',
    })

    assert result == 'fake-model'
    assert captured['model'] == 'BAAI/bge-reranker-v2-m3'
    generated = yaml.safe_load(Path(captured['config']).read_text(encoding='utf-8'))
    assert generated == {
        'BAAI/bge-reranker-v2-m3': [{
            'source': 'siliconflow',
            'type': 'rerank',
            'model': 'BAAI/bge-reranker-v2-m3',
            'api_key': 'secret-key',
        }]
    }


@pytest.mark.skipif(get_models_mod is None,
                    reason="chat.pipelines.builders.get_models module has been removed")
def test_runtime_auto_model_dir_cleanup_removes_generated_files(tmp_path, monkeypatch):
    runtime_dir = tmp_path / 'runtime-auto-model'
    runtime_dir.mkdir()
    generated = runtime_dir / 'foo.yaml'
    generated.write_text('foo: bar\n', encoding='utf-8')
    monkeypatch.setattr(get_models_mod, '_RUNTIME_AUTO_MODEL_DIR', runtime_dir)

    get_models_mod._cleanup_runtime_auto_model_dir()

    assert not runtime_dir.exists()
