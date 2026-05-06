def test_config_reads_custom_environment_values(monkeypatch):
    # Config is a singleton; patch env vars and read directly from the config instance.
    monkeypatch.setenv('LAZYRAG_MOUNT_BASE_DIR', '/mnt/data')
    monkeypatch.setenv('LAZYRAG_SENSITIVE_WORDS_PATH', '/tmp/words.txt')
    monkeypatch.setenv('LAZYRAG_LLM_PRIORITY', '12')
    monkeypatch.setenv('LAZYRAG_MAX_CONCURRENCY', '7')
    monkeypatch.setenv('LAZYRAG_RAG_MODE', 'false')
    monkeypatch.setenv('LAZYRAG_MULTIMODAL_MODE', 'false')
    monkeypatch.setenv('LAZYRAG_ALGO_SERVICE_URL', 'http://algo-service:9000/')
    monkeypatch.setenv('LAZYRAG_ALGO_DATASET_NAME', 'science')
    monkeypatch.setenv('LAZYRAG_DEFAULT_CHAT_DATASET', 'science')

    from config import config as _cfg
    assert _cfg['mount_base_dir'] == '/mnt/data'
    assert _cfg['sensitive_words_path'] == '/tmp/words.txt'
    assert _cfg['llm_priority'] == 12
    assert _cfg['max_concurrency'] == 7
    assert _cfg['rag_mode'] is False
    assert _cfg['multimodal_mode'] is False
    assert _cfg['algo_service_url'].rstrip('/') == 'http://algo-service:9000'
    assert _cfg['algo_dataset_name'] == 'science'
    assert _cfg['default_chat_dataset'] == 'science'


def test_config_falls_back_to_defaults(monkeypatch):
    monkeypatch.delenv('LAZYRAG_LLM_PRIORITY', raising=False)
    monkeypatch.delenv('LAZYRAG_RAG_MODE', raising=False)
    monkeypatch.delenv('LAZYRAG_MULTIMODAL_MODE', raising=False)

    from config import config as _cfg
    assert _cfg['llm_priority'] == 0
    assert _cfg['rag_mode'] is True
    assert _cfg['multimodal_mode'] is True
