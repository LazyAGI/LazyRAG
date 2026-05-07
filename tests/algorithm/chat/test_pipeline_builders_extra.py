"""
Additional tests for pipeline builder helpers.

These tests are kept in a separate file because importing
chat.pipelines.builders.get_ppl_search triggers a circular import
(vocab.evolution → chat.pipelines.builders) when the full vocab package
is loaded.  We break the cycle by injecting a lightweight stub for
vocab.vocab_manager into sys.modules before the real import happens.
"""
import importlib
import sys
import types
from types import SimpleNamespace


def _stub_vocab():
    """Inject a minimal vocab.vocab_manager stub to prevent circular import."""
    stub = types.ModuleType('vocab.vocab_manager')
    stub.get_vocab_manager = lambda user_id: (lambda q: q)
    sys.modules.setdefault('vocab', types.ModuleType('vocab'))
    sys.modules['vocab.vocab_manager'] = stub

    # Also stub vocab.evolution so vocab/__init__ doesn't pull in the real one
    evo_stub = types.ModuleType('vocab.evolution')
    sys.modules['vocab.evolution'] = evo_stub

    # Stub vocab.db to avoid psycopg2 / sqlalchemy at import time
    db_stub = types.ModuleType('vocab.db')
    sys.modules['vocab.db'] = db_stub


_stub_vocab()

retriever_mod = importlib.import_module('chat.pipelines.builders.get_retriever')
ppl_search_mod = importlib.import_module('chat.pipelines.builders.get_ppl_search')


# ---------------------------------------------------------------------------
# _build_default_retriever_configs — topk and embed_keys propagation
# ---------------------------------------------------------------------------

def test_build_default_retriever_configs_uses_topk_and_embed_keys(monkeypatch):
    monkeypatch.setattr(retriever_mod, 'get_embed_keys', lambda: ['embed_main', 'embed_sparse'])

    configs = retriever_mod._build_default_retriever_configs(topk=15)

    assert len(configs) == 2
    names = [c['group_name'] for c in configs]
    assert 'line' in names
    assert 'block' in names
    for cfg in configs:
        assert cfg['topk'] == 15
        assert cfg['embed_keys'] == ['embed_main', 'embed_sparse']


def test_build_default_retriever_configs_falls_back_to_embed_main(monkeypatch):
    monkeypatch.setattr(retriever_mod, 'get_embed_keys', lambda: [])

    configs = retriever_mod._build_default_retriever_configs()

    for cfg in configs:
        assert cfg['embed_keys'] == [retriever_mod.EMBED_MAIN]


def test_build_default_retriever_configs_line_has_block_target(monkeypatch):
    monkeypatch.setattr(retriever_mod, 'get_embed_keys', lambda: ['embed_main'])

    configs = retriever_mod._build_default_retriever_configs()

    line_cfg = next(c for c in configs if c['group_name'] == 'line')
    assert line_cfg.get('target') == 'block'
    block_cfg = next(c for c in configs if c['group_name'] == 'block')
    assert 'target' not in block_cfg


# ---------------------------------------------------------------------------
# parse_query — vocab manager integration
# ---------------------------------------------------------------------------

def test_parse_query_delegates_to_vocab_manager(monkeypatch):
    calls = []

    def fake_get_vocab_manager(user_id):
        calls.append(user_id)
        return lambda q: f'expanded:{q}'

    monkeypatch.setattr(ppl_search_mod, 'get_vocab_manager', fake_get_vocab_manager)

    result = ppl_search_mod.parse_query({'query': 'hello', 'create_user_id': 'user-1'})

    assert result == 'expanded:hello'
    assert calls == ['user-1']


def test_parse_query_uses_empty_user_id_when_missing(monkeypatch):
    monkeypatch.setattr(ppl_search_mod, 'get_vocab_manager', lambda uid: lambda q: f'{uid}:{q}')

    result = ppl_search_mod.parse_query({'query': 'test'})

    assert result == ':test'


# ---------------------------------------------------------------------------
# merge_rank_results — multi-route result merging
# ---------------------------------------------------------------------------

def test_merge_rank_results_filters_empty_lists():
    r1 = ['node-a', 'node-b']
    r2 = []
    r3 = ['node-c']

    result = ppl_search_mod.merge_rank_results(r1, r2, r3)

    assert result == (r1, r3)


def test_merge_rank_results_returns_empty_tuple_when_all_empty():
    assert ppl_search_mod.merge_rank_results([], []) == ()
