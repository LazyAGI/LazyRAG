import importlib
import sys


def _reload_config_module(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    sys.modules.pop('chat.config', None)
    return importlib.import_module('chat.config')


def test_config_reads_custom_environment_values(monkeypatch):
    config = _reload_config_module(
        monkeypatch,
        LAZYLLM_MOUNT_DIR='/mnt/data',
        SENSITIVE_WORDS_PATH='/tmp/words.txt',
        LAZYRAG_LLM_PRIORITY='12',
        MAX_CONCURRENCY='7',
        RAG_MODE='false',
        MULTIMODAL_MODE='false',
        LAZYRAG_ALGO_SERVICE_URL='http://algo-service:9000/',
        LAZYRAG_ALGO_DATASET_NAME='science',
        LAZYRAG_DEFAULT_CHAT_DATASET='science',
    )

    assert config.MOUNT_BASE_DIR == '/mnt/data'
    assert config.SENSITIVE_WORDS_PATH == '/tmp/words.txt'
    assert config.LAZYRAG_LLM_PRIORITY == 12
    assert config.MAX_CONCURRENCY == 7
    assert config.RAG_MODE is False
    assert config.MULTIMODAL_MODE is False
    assert config.DEFAULT_ALGO_SERVICE_URL == 'http://algo-service:9000'
    assert config.DEFAULT_ALGO_DATASET_NAME == 'science'
    assert config.DEFAULT_CHAT_DATASET == 'science'
    assert config.URL_MAP['algo'] == 'http://algo-service:9000,science'
    assert config.URL_MAP['default'] == 'http://algo-service:9000,science'


def test_config_falls_back_when_priority_is_not_numeric(monkeypatch):
    config = _reload_config_module(
        monkeypatch,
        LAZYRAG_LLM_PRIORITY='not-a-number',
        RAG_MODE=None,
        MULTIMODAL_MODE=None,
    )

    assert config.LAZYRAG_LLM_PRIORITY == 0
    assert config.RAG_MODE is True
    assert config.MULTIMODAL_MODE is True
