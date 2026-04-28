"""Tests for multi-user VocabManager and vocab hot-reload API.

Test categories
---------------
- TestVocabManagerBasic        : single-user VocabManager with injected data_source
- TestVocabManagerReload       : reload() refreshes the AC automaton
- TestVocabRegistry            : get_vocab_manager() per-user isolation
- TestVocabManagerThreadSafety : concurrent reload + call
- TestVocabReloadRoute         : FastAPI POST /api/vocab/reload
- TestVocabDBIntegration       : real PostgreSQL queries (requires LAZYRAG_DATABASE_URL)

Run (from repo root, with lazyllm env activated):
    source activate lazyllm
    cd LazyLLM && export PYTHONPATH=$PWD:$PYTHONPATH && cd ../LazyRAG
    python -m pytest tests/algorithm/test_vocab_manager.py -v

Integration tests only:
    LAZYRAG_DATABASE_URL=postgresql://root:123456@10.119.24.129:5432/app \
        python -m pytest tests/algorithm/test_vocab_manager.py -v -m integration
"""
from __future__ import annotations

import importlib
import os as _os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure algorithm/ is on sys.path
# ---------------------------------------------------------------------------
_ALGO = _os.path.join(_os.path.dirname(__file__), '..', '..', 'algorithm')
if _ALGO not in sys.path:
    sys.path.insert(0, _ALGO)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_ROWS_USER1 = [
    {'word': '苹果',  'cluster_id': '01'},
    {'word': 'apple', 'cluster_id': '01'},
    {'word': '苹果',  'cluster_id': '02'},   # same word, different cluster
    {'word': 'apple', 'cluster_id': '02'},
]

_SAMPLE_ROWS_USER2 = [
    {'word': '民法',    'cluster_id': 'g1'},
    {'word': '民事法律','cluster_id': 'g1'},
]


def _make_manager(rows: list, create_user_id: str = 'test_user'):
    """Create an isolated VocabManager using an in-memory data_source (no DB)."""
    from vocab.vocab_manager import VocabManager
    return VocabManager(create_user_id=create_user_id, data_source=rows)


def _reset_registry():
    """Clear the global registry between tests."""
    from vocab.vocab_manager import clear_registry
    clear_registry()


# ---------------------------------------------------------------------------
# TestVocabManagerBasic
# ---------------------------------------------------------------------------

class TestVocabManagerBasic:

    def test_empty_vocab_query_unchanged(self):
        mgr = _make_manager([])
        assert mgr('任意查询') == '任意查询'
        assert mgr(['a', 'b']) == ['a', 'b']

    def test_vocab_size_reflects_loaded_entries(self):
        mgr = _make_manager(_SAMPLE_ROWS_USER1)
        # word_to_cluster key is the word string; 苹果/apple appear in two clusters
        # but QueryEnhACProcessor deduplicates by word (last wins)
        assert mgr.vocab_size == 2  # unique words: '苹果', 'apple'

    def test_create_user_id_property(self):
        mgr = _make_manager([], create_user_id='alice')
        assert mgr.create_user_id == 'alice'

    def test_call_with_string_no_discriminator(self):
        """With discriminator=None, AC matches are skipped → query unchanged."""
        mgr = _make_manager(_SAMPLE_ROWS_USER2)
        # discriminator=None means words are detected but enhancement is skipped
        result = mgr('关于民法的问题')
        assert isinstance(result, str)

    def test_call_with_list(self):
        mgr = _make_manager([])
        result = mgr(['query1', 'query2'])
        assert result == ['query1', 'query2']


# ---------------------------------------------------------------------------
# TestVocabManagerReload
# ---------------------------------------------------------------------------

class TestVocabManagerReload:

    def test_reload_updates_vocab(self):
        mgr = _make_manager([], create_user_id='u_reload')
        assert mgr.vocab_size == 0

        new_rows = [
            {'word': 'alpha', 'cluster_id': 'c1'},
            {'word': 'beta',  'cluster_id': 'c1'},
        ]
        # Patch _load_from_db so reload() reads new_rows
        with patch.object(mgr, '_load_from_db', return_value=new_rows):
            count = mgr.reload()
        assert count == 2
        assert mgr.vocab_size == 2

    def test_reload_clears_stale_vocab(self):
        old_rows = [{'word': 'stale', 'cluster_id': 'x'}]
        mgr = _make_manager(old_rows)
        assert mgr.vocab_size == 1

        with patch.object(mgr, '_load_from_db', return_value=[]):
            mgr.reload()
        assert mgr.vocab_size == 0

    def test_reload_without_db_returns_zero(self):
        """When DB returns empty, reload gives vocab_size=0."""
        mgr = _make_manager([{'word': 'existing', 'cluster_id': 'x'}])
        assert mgr.vocab_size == 1
        # Patch the module-level fetch_vocab_for_create_user_id that _load_from_db calls
        with patch('vocab.vocab_manager.fetch_vocab_for_create_user_id', return_value=[]):
            mgr.reload()
        assert mgr.vocab_size == 0


# ---------------------------------------------------------------------------
# TestVocabRegistry
# ---------------------------------------------------------------------------

class TestVocabRegistry:

    def setup_method(self):
        _reset_registry()

    def teardown_method(self):
        _reset_registry()

    def test_different_users_get_different_managers(self):
        from vocab.vocab_manager import get_vocab_manager
        with patch('vocab.vocab_manager.fetch_vocab_for_create_user_id', return_value=[]):
            mgr_a = get_vocab_manager('alice')
            mgr_b = get_vocab_manager('bob')
        assert mgr_a is not mgr_b
        assert mgr_a.create_user_id == 'alice'
        assert mgr_b.create_user_id == 'bob'

    def test_same_user_gets_same_manager_instance(self):
        from vocab.vocab_manager import get_vocab_manager
        with patch('vocab.vocab_manager.fetch_vocab_for_create_user_id', return_value=[]):
            mgr1 = get_vocab_manager('charlie')
            mgr2 = get_vocab_manager('charlie')
        assert mgr1 is mgr2

    def test_user_isolation_vocab_does_not_bleed(self):
        """user_001's vocab should not affect user_002's query."""
        from vocab.vocab_manager import get_vocab_manager

        def _side_effect(create_user_id):
            return _SAMPLE_ROWS_USER1 if create_user_id == 'user_001' else _SAMPLE_ROWS_USER2

        # patch the name used inside vocab_manager.py (from .db import fetch_vocab_for_create_user_id)
        with patch('vocab.vocab_manager.fetch_vocab_for_create_user_id', side_effect=_side_effect):
            mgr1 = get_vocab_manager('user_001')
            mgr2 = get_vocab_manager('user_002')

        # user_001 has '苹果'/'apple' — user_002 should NOT
        assert '苹果' in mgr1._proc.word_to_cluster
        assert '苹果' not in mgr2._proc.word_to_cluster

        # user_002 has '民法' — user_001 should NOT
        assert '民法' in mgr2._proc.word_to_cluster
        assert '民法' not in mgr1._proc.word_to_cluster

    def test_empty_create_user_id_allowed(self):
        from vocab.vocab_manager import get_vocab_manager
        with patch('vocab.vocab_manager.fetch_vocab_for_create_user_id', return_value=[]):
            mgr = get_vocab_manager('')
        assert mgr.create_user_id == ''
        assert mgr.vocab_size == 0


# ---------------------------------------------------------------------------
# TestVocabManagerThreadSafety
# ---------------------------------------------------------------------------

class TestVocabManagerThreadSafety:

    def test_concurrent_reload_and_call_no_exception(self):  # noqa: D401
        rows = [
            {'word': 'threadtok', 'cluster_id': 'th'},
            {'word': 'tok2',      'cluster_id': 'th'},
        ]
        mgr = _make_manager(rows, create_user_id='thread_user')
        errors: list = []

        def _reload():
            try:
                for _ in range(20):
                    with patch.object(mgr, '_load_from_db', return_value=rows):
                        mgr.reload()
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        def _call():
            try:
                for _ in range(20):
                    mgr('threadtok test')
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=_reload) for _ in range(3)]
        threads += [threading.Thread(target=_call) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f'Thread errors: {errors}'


# ---------------------------------------------------------------------------
# TestVocabReloadRoute
# ---------------------------------------------------------------------------

class TestVocabReloadRoute:

    @pytest.fixture()
    def client(self, tmp_path):
        """Build a minimal FastAPI test app with vocab_routes registered."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        # Load vocab_routes without triggering ChatServer (which needs model files)
        _routes_file = _os.path.join(_ALGO, 'chat', 'app', 'api', 'vocab_routes.py')
        spec = importlib.util.spec_from_file_location('_vocab_routes_test', _routes_file)
        vocab_routes_mod = importlib.util.module_from_spec(spec)

        # Patch get_vocab_manager inside the routes module
        mock_mgr = MagicMock()
        mock_mgr.reload.return_value = 3
        mock_extract = MagicMock(return_value=[{
            'reason': '用户明确要求记住苹果就是 apple',
            'words': ['苹果', 'apple'],
            'description': '水果语境',
            'group_ids': '[]',
            'create_user_id': 'user_001',
            'message_ids': '["m1"]',
            'action': 'create_new_group',
        }])

        with patch('vocab.vocab_manager.get_vocab_manager', return_value=mock_mgr), \
             patch('vocab.run_vocab_evolution', mock_extract):
            spec.loader.exec_module(vocab_routes_mod)
            test_app.include_router(vocab_routes_mod.router)

        yield TestClient(test_app), mock_mgr, mock_extract

    def test_reload_returns_ok_with_create_user_id(self, client):
        tc, mock_mgr, _ = client
        resp = tc.post('/api/vocab/reload', json={'create_user_id': 'user_001'})
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert body['create_user_id'] == 'user_001'
        assert isinstance(body['vocab_size'], int)

    def test_reload_default_empty_create_user_id(self, client):
        tc, _, _ = client
        resp = tc.post('/api/vocab/reload')
        assert resp.status_code == 200
        assert resp.json()['create_user_id'] == ''

    def test_extract_returns_no_content_with_create_user_id(self, client):
        tc, _, mock_extract = client
        resp = tc.post('/api/vocab/extract', json={'create_user_id': 'user_001'})

        assert resp.status_code == 204
        assert resp.content == b''
        mock_extract.assert_called_once_with({'create_user_id': 'user_001'})

    def test_extract_without_create_user_id_runs_for_all_users(self, client):
        tc, _, mock_extract = client
        resp = tc.post('/api/vocab/extract')

        assert resp.status_code == 204
        assert resp.content == b''
        mock_extract.assert_called_once_with(None)

    def test_reload_different_create_user_ids_call_respective_manager(self, tmp_path):
        """Each create_user_id triggers reload on its own VocabManager instance."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from vocab.vocab_manager import clear_registry

        clear_registry()

        test_app = FastAPI()
        _routes_file = _os.path.join(_ALGO, 'chat', 'app', 'api', 'vocab_routes.py')
        spec = importlib.util.spec_from_file_location('_vocab_routes_multi', _routes_file)
        vocab_routes_mod = importlib.util.module_from_spec(spec)

        called_users: list = []

        def fake_get_manager(uid=''):
            called_users.append(uid)
            m = MagicMock()
            m.reload.return_value = 0
            return m

        with patch('vocab.vocab_manager.get_vocab_manager', side_effect=fake_get_manager):
            spec.loader.exec_module(vocab_routes_mod)
            test_app.include_router(vocab_routes_mod.router)
            tc = TestClient(test_app)
            tc.post('/api/vocab/reload', json={'create_user_id': 'alice'})
            tc.post('/api/vocab/reload', json={'create_user_id': 'bob'})

        assert 'alice' in called_users
        assert 'bob' in called_users
        clear_registry()



# ---------------------------------------------------------------------------
# TestVocabDBIntegration  (requires real DB — skipped when env var absent)
# ---------------------------------------------------------------------------

_DB_URL = _os.getenv('LAZYRAG_DATABASE_URL', '')


@pytest.mark.integration
@pytest.mark.skipif(not _DB_URL, reason='LAZYRAG_DATABASE_URL not set')
class TestVocabDBIntegration:
    """Integration tests that hit the real lazyrag_vocab table."""

    def test_fetch_vocab_for_create_user_id_user001(self):
        from vocab.db import fetch_vocab_for_create_user_id
        rows = fetch_vocab_for_create_user_id('user_001')
        assert len(rows) >= 4, f'expected ≥4 rows for user_001, got {rows}'
        words = {r['word'] for r in rows}
        assert '苹果' in words
        assert 'apple' in words

    def test_fetch_vocab_for_create_user_id_user002(self):
        from vocab.db import fetch_vocab_for_create_user_id
        rows = fetch_vocab_for_create_user_id('user_002')
        words = {r['word'] for r in rows}
        assert '民法' in words
        assert '民事法律' in words

    def test_fetch_vocab_unknown_user_returns_empty(self):
        from vocab.db import fetch_vocab_for_create_user_id
        rows = fetch_vocab_for_create_user_id('__nonexistent_user_xyz__')
        assert rows == []

    def test_vocab_manager_loads_from_db(self):
        _reset_registry()
        from vocab.vocab_manager import get_vocab_manager
        mgr = get_vocab_manager('user_001')
        assert mgr.vocab_size >= 2   # at least 苹果, apple (deduped by word)
        _reset_registry()

    def test_reload_reads_db(self):
        _reset_registry()
        from vocab.vocab_manager import get_vocab_manager
        mgr = get_vocab_manager('user_002')
        count = mgr.reload()
        assert count >= 2
        _reset_registry()

    def test_user_isolation_in_full_stack(self):
        """user_001 and user_002 managers are completely independent."""
        _reset_registry()
        from vocab.vocab_manager import get_vocab_manager
        mgr1 = get_vocab_manager('user_001')
        mgr2 = get_vocab_manager('user_002')

        assert '苹果'    in mgr1._proc.word_to_cluster
        assert '苹果'    not in mgr2._proc.word_to_cluster
        assert '民法'    in mgr2._proc.word_to_cluster
        assert '民法'    not in mgr1._proc.word_to_cluster
        _reset_registry()
