"""
Additional tests for kb tool helpers (filters, temp_files, no-parent node).

The chat.tools.kb module imports chat.pipelines.builders which triggers a
circular import via vocab.evolution.  We break the cycle with the same
lightweight stub approach used in test_pipeline_builders_extra.py.
"""
import sys
import types


def _stub_vocab_and_chat_pipelines():
    """Stub out modules that cause circular imports at collection time.

    vocab.evolution is NOT stubbed here because the circular import
    (vocab.evolution → chat.pipelines.builders) has been resolved with lazy
    imports inside the class constructors.  Stubbing vocab.evolution would
    leave an empty module object in sys.modules and break any later test that
    imports real symbols from it (e.g. ActionPlanningModule).
    """
    # vocab stubs — only inject if not already loaded
    vocab_pkg = types.ModuleType('vocab')
    sys.modules.setdefault('vocab', vocab_pkg)

    if 'vocab.vocab_manager' not in sys.modules:
        vm_stub = types.ModuleType('vocab.vocab_manager')
        vm_stub.get_vocab_manager = lambda user_id: (lambda q: q)
        sys.modules['vocab.vocab_manager'] = vm_stub

    if 'vocab.db' not in sys.modules:
        db_stub = types.ModuleType('vocab.db')
        sys.modules['vocab.db'] = db_stub


_stub_vocab_and_chat_pipelines()

from chat.tools import kb  # noqa: E402  (must come after stubs)

DEFAULT_AGENTIC_CONFIG = {
    'kb_url': 'http://10.119.24.129:8056',
    'kb_name': 'general_algo',
    'kb_id': 'ds_9e96150bb1ceeec7d96055638072b8a9',
    'es_url': 'https://10.119.24.129:9200',
    'es_user': 'admin',
    'es_password': 'LazyRAG_OpenSearch123!',
}


# ---------------------------------------------------------------------------
# kb_search — explicit filters merged with kb_id
# ---------------------------------------------------------------------------

def test_kb_search_merges_explicit_filters_with_kb_id(monkeypatch):
    captured_payload = {}

    def fake_get_ppl_search(url, retriever_configs=None, topk=20, k_max=10):
        def fake_search(payload):
            captured_payload.update(payload)
            return []
        return fake_search

    monkeypatch.setattr(kb, 'get_ppl_search', fake_get_ppl_search)
    original_config = kb.lazyllm.globals.get('agentic_config')
    kb.lazyllm.globals['agentic_config'] = DEFAULT_AGENTIC_CONFIG
    try:
        kb.kb_search('query', filters={'file_name': 'report.pdf'})
    finally:
        kb.lazyllm.globals['agentic_config'] = original_config or {}

    assert captured_payload['filters']['file_name'] == 'report.pdf'
    assert captured_payload['filters']['kb_id'] == DEFAULT_AGENTIC_CONFIG['kb_id']


def test_kb_search_uses_temp_files_from_agentic_config(monkeypatch):
    captured_payload = {}

    def fake_get_ppl_search(url, retriever_configs=None, topk=20, k_max=10):
        def fake_search(payload):
            captured_payload.update(payload)
            return []
        return fake_search

    monkeypatch.setattr(kb, 'get_ppl_search', fake_get_ppl_search)
    config_with_files = dict(DEFAULT_AGENTIC_CONFIG, temp_files=['file-a', 'file-b'])
    original_config = kb.lazyllm.globals.get('agentic_config')
    kb.lazyllm.globals['agentic_config'] = config_with_files
    try:
        kb.kb_search('query')
    finally:
        kb.lazyllm.globals['agentic_config'] = original_config or {}

    assert captured_payload['files'] == ['file-a', 'file-b']


def test_kb_search_explicit_empty_files_overrides_temp_files(monkeypatch):
    captured_payload = {}

    def fake_get_ppl_search(url, retriever_configs=None, topk=20, k_max=10):
        def fake_search(payload):
            captured_payload.update(payload)
            return []
        return fake_search

    monkeypatch.setattr(kb, 'get_ppl_search', fake_get_ppl_search)
    config_with_files = dict(DEFAULT_AGENTIC_CONFIG, temp_files=['file-a'])
    original_config = kb.lazyllm.globals.get('agentic_config')
    kb.lazyllm.globals['agentic_config'] = config_with_files
    try:
        kb.kb_search('query', files=[])
    finally:
        kb.lazyllm.globals['agentic_config'] = original_config or {}

    assert captured_payload['files'] == []


# ---------------------------------------------------------------------------
# kb_get_parent_node — node without parent returns empty items
# ---------------------------------------------------------------------------

def test_kb_get_parent_node_returns_empty_when_no_parent(monkeypatch):
    def fake_opensearch_search(index, body, config):
        return {
            'hits': {
                'hits': [{
                    '_id': 'root-node',
                    '_source': {
                        'uid': 'root-node',
                        'number': 1,
                        'group': 'block',
                        'parent': None,
                        'doc_id': 'doc-1',
                        'kb_id': DEFAULT_AGENTIC_CONFIG['kb_id'],
                        'content': 'root text',
                    },
                }]
            }
        }

    monkeypatch.setattr(kb, '_opensearch_search', fake_opensearch_search)
    original_config = kb.lazyllm.globals.get('agentic_config')
    kb.lazyllm.globals['agentic_config'] = DEFAULT_AGENTIC_CONFIG
    try:
        result = kb.kb_get_parent_node('root-node')
    finally:
        kb.lazyllm.globals['agentic_config'] = original_config or {}

    assert result['node_id'] == 'root-node'
    assert result['parent_id'] is None
    assert result['total'] == 0
    assert result['items'] == []
