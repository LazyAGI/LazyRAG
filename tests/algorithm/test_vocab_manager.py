"""Tests for VocabManager and vocab hot-reload API.

Tests cover:
- VocabManager returns query unchanged when vocab is empty
- VocabManager.reload() updates vocab from a JSON file
- VocabManager.reload() with a new file_path
- VocabManager.reload() gracefully handles missing / malformed files
- VocabManager.__call__() passes through to QueryEnhACProcessor
- Thread-safety: concurrent reload + call does not raise
- FastAPI route POST /api/vocab/reload returns correct response
"""
from __future__ import annotations

import json
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure algorithm/ is on sys.path so `from vocab...` and `from chat...` work.
# The conftest.py in this directory already does this, but be explicit in case
# the file is run directly.
# ---------------------------------------------------------------------------
import os as _os

_ALGO = _os.path.join(_os.path.dirname(__file__), '..', '..', 'algorithm')
if _ALGO not in sys.path:
    sys.path.insert(0, _ALGO)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vocab(tmp_path, rows: list) -> str:
    tmp_path = _os.path.join(str(tmp_path))  # accept both Path and str
    _os.makedirs(tmp_path, exist_ok=True)
    import pathlib
    p = pathlib.Path(tmp_path) / 'vocab.json'
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return str(p)


def _fresh_manager(vocab_file: str = ''):
    """Create an isolated VocabManager (bypasses the global singleton)."""
    from vocab.vocab_manager import VocabManager
    with patch.dict(_os.environ, {'LAZYRAG_VOCAB_FILE_PATH': vocab_file}):
        mgr = VocabManager()
    return mgr


# ---------------------------------------------------------------------------
# VocabManager unit tests
# ---------------------------------------------------------------------------

class TestVocabManagerBasic:

    def test_empty_vocab_query_unchanged(self, tmp_path):
        """With no vocab file / empty vocab the query passes through unchanged."""
        path = _make_vocab(tmp_path, [])
        mgr = _fresh_manager(path)
        assert mgr('任意查询') == '任意查询'
        assert mgr(['a', 'b']) == ['a', 'b']

    def test_vocab_size_reflects_loaded_entries(self, tmp_path):
        rows = [
            {'cluster_id': 'c1', 'word': 'alpha'},
            {'cluster_id': 'c1', 'word': 'beta'},
            {'cluster_id': 'c2', 'word': 'gamma'},
        ]
        path = _make_vocab(tmp_path, rows)
        mgr = _fresh_manager(path)
        assert mgr.vocab_size == 3

    def test_file_path_property(self, tmp_path):
        path = _make_vocab(tmp_path, [])
        mgr = _fresh_manager(path)
        assert mgr.file_path == path

    def test_missing_vocab_file_returns_empty_vocab(self, tmp_path):
        missing = str(tmp_path / 'nonexistent.json')
        mgr = _fresh_manager(missing)
        assert mgr.vocab_size == 0
        assert mgr('hello') == 'hello'

    def test_malformed_vocab_file_returns_empty_vocab(self, tmp_path):
        bad = tmp_path / 'bad.json'
        bad.write_text('not valid json', encoding='utf-8')
        mgr = _fresh_manager(str(bad))
        assert mgr.vocab_size == 0

    def test_non_list_root_vocab_file_returns_empty_vocab(self, tmp_path):
        p = tmp_path / 'obj.json'
        p.write_text('{"key": "value"}', encoding='utf-8')
        mgr = _fresh_manager(str(p))
        assert mgr.vocab_size == 0


class TestVocabManagerReload:

    def test_reload_updates_vocab(self, tmp_path):
        empty = _make_vocab(tmp_path, [])
        mgr = _fresh_manager(empty)
        assert mgr.vocab_size == 0

        rows = [
            {'cluster_id': 'k', 'word': 'reloadtoken'},
            {'cluster_id': 'k', 'word': 'reload_alias'},
        ]
        full = _make_vocab(tmp_path, rows)
        count = mgr.reload(file_path=full)
        assert count == 2
        assert mgr.vocab_size == 2

    def test_reload_without_new_path_reuses_current_path(self, tmp_path):
        rows = [{'cluster_id': 'x', 'word': 'tok'}]
        path = _make_vocab(tmp_path, rows)
        mgr = _fresh_manager(path)
        assert mgr.vocab_size == 1
        count = mgr.reload()
        assert count == 1

    def test_reload_with_new_path_updates_file_path(self, tmp_path):
        old = _make_vocab(tmp_path, [])
        mgr = _fresh_manager(old)

        new_rows = [{'cluster_id': 'y', 'word': 'newtok'}]
        new_path = _make_vocab(tmp_path / 'sub', new_rows)  # sub dir created by tmp_path fixture
        mgr.reload(file_path=new_path)
        assert mgr.file_path == new_path
        assert mgr.vocab_size == 1

    def test_reload_missing_file_empties_vocab(self, tmp_path):
        rows = [{'cluster_id': 'z', 'word': 'exists'}]
        path = _make_vocab(tmp_path, rows)
        mgr = _fresh_manager(path)
        assert mgr.vocab_size == 1

        mgr.reload(file_path=str(tmp_path / 'gone.json'))
        assert mgr.vocab_size == 0


class TestVocabManagerThreadSafety:

    def test_concurrent_reload_and_call_no_exception(self, tmp_path):
        rows = [{'cluster_id': 'th', 'word': 'threadtok'}]
        path = _make_vocab(tmp_path, rows)
        mgr = _fresh_manager(path)

        errors: list = []

        def _reload():
            try:
                for _ in range(20):
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
# FastAPI route tests
# ---------------------------------------------------------------------------

class TestVocabReloadRoute:

    @pytest.fixture()
    def app(self, tmp_path):
        """Build a minimal FastAPI test app with vocab_routes registered."""
        import importlib.util
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        # Patch get_vocab_manager to return an isolated manager so tests are
        # independent of the global singleton.
        rows = [{'cluster_id': 'r', 'word': 'routetok'}]
        vocab_file = _make_vocab(tmp_path, rows)
        with patch.dict(_os.environ, {'LAZYRAG_VOCAB_FILE_PATH': vocab_file}):
            from vocab.vocab_manager import VocabManager
            mock_mgr = VocabManager()

        # Import vocab_routes directly (bypassing chat.app.api.__init__ which
        # would trigger the full ChatServer singleton requiring model files).
        _routes_file = _os.path.join(_ALGO, 'chat', 'app', 'api', 'vocab_routes.py')
        spec = importlib.util.spec_from_file_location('_vocab_routes_test', _routes_file)
        vocab_routes_mod = importlib.util.module_from_spec(spec)

        with patch('vocab.vocab_manager.get_vocab_manager', return_value=mock_mgr):
            spec.loader.exec_module(vocab_routes_mod)
            test_app.include_router(vocab_routes_mod.router)
            client = TestClient(test_app)
            yield client, mock_mgr

    def test_reload_returns_ok(self, app):
        client, _ = app
        resp = client.post('/api/vocab/reload')
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert isinstance(body['vocab_size'], int)

    def test_reload_with_new_file_path(self, app, tmp_path):
        client, mgr = app
        new_rows = [
            {'cluster_id': 'nr', 'word': 'newtok1'},
            {'cluster_id': 'nr', 'word': 'newtok2'},
        ]
        new_file = _make_vocab(tmp_path / 'new', new_rows)
        resp = client.post('/api/vocab/reload', json={'file_path': new_file})
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert body['vocab_size'] == 2
        assert mgr.file_path == new_file

    def test_reload_missing_file_returns_zero_size(self, app, tmp_path):
        client, _ = app
        missing = str(tmp_path / 'nope.json')
        resp = client.post('/api/vocab/reload', json={'file_path': missing})
        assert resp.status_code == 200
        assert resp.json()['vocab_size'] == 0
