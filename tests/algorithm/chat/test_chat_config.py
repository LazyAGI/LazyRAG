import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def test_config_reads_custom_environment_values(monkeypatch):
    # Config is a singleton; patch env vars and read directly from the config instance.
    monkeypatch.setenv('LAZYMIND_MOUNT_BASE_DIR', '/mnt/data')
    monkeypatch.setenv('LAZYMIND_SENSITIVE_WORDS_PATH', '/tmp/words.txt')
    monkeypatch.setenv('LAZYMIND_LLM_PRIORITY', '12')
    monkeypatch.setenv('LAZYMIND_MAX_CONCURRENCY', '7')
    monkeypatch.setenv('LAZYMIND_RAG_MODE', 'false')
    monkeypatch.setenv('LAZYMIND_MULTIMODAL_MODE', 'false')
    monkeypatch.setenv('LAZYMIND_ALGO_SERVICE_URL', 'http://algo-service:9000/')
    monkeypatch.setenv('LAZYMIND_ALGO_DATASET_NAME', 'science')
    monkeypatch.setenv('LAZYMIND_DEFAULT_CHAT_DATASET', 'science')
    monkeypatch.setenv('LAZYMIND_DATASET_URL_MAP', '{"custom":"http://kb-service:9100,custom_kb"}')

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
    assert _cfg['dataset_url_map'] == '{"custom":"http://kb-service:9100,custom_kb"}'


def test_config_falls_back_to_defaults(monkeypatch):
    monkeypatch.delenv('LAZYMIND_LLM_PRIORITY', raising=False)
    monkeypatch.delenv('LAZYMIND_RAG_MODE', raising=False)
    monkeypatch.delenv('LAZYMIND_MULTIMODAL_MODE', raising=False)

    from config import config as _cfg
    assert _cfg['llm_priority'] == 0
    assert _cfg['rag_mode'] is True
    assert _cfg['multimodal_mode'] is True


def test_chat_config_resolves_dataset_binding_from_env_override(monkeypatch):
    monkeypatch.setenv('LAZYMIND_ALGO_SERVICE_URL', 'http://algo-service:9000/')
    monkeypatch.setenv('LAZYMIND_ALGO_DATASET_NAME', 'science')
    monkeypatch.setenv('LAZYMIND_DATASET_URL_MAP', '{"custom":"http://kb-service:9100,custom_kb"}')

    import chat.config as chat_config

    chat_config = importlib.reload(chat_config)

    assert chat_config.resolve_dataset_binding('custom') == ('http://kb-service:9100', 'custom_kb')
    assert chat_config.resolve_dataset_binding('algo') == ('http://algo-service:9000', 'science')
    assert chat_config.resolve_dataset_binding('ds_runtime') == ('http://algo-service:9000', 'ds_runtime')


def test_chat_config_bootstraps_canonical_config_module(monkeypatch):
    fake_config_module = ModuleType('config')
    fake_config_module.config = object()
    monkeypatch.setitem(sys.modules, 'config', fake_config_module)

    module_name = 'test_chat_config_isolated'
    module_path = Path(__file__).resolve().parents[3] / 'algorithm/chat/config.py'
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert Path(sys.modules['config'].__file__).resolve() == (
        Path(__file__).resolve().parents[3] / 'algorithm/config.py'
    ).resolve()
    assert module.config['dataset_url_map'] == ''
    assert module.DEFAULT_CHAT_DATASET == 'algo'
    assert module.resolve_dataset_binding('algo') == ('http://lazyllm-algo:8000', 'general_algo')
