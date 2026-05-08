from __future__ import annotations

import os
import sys


_ALGO = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'algorithm')
_LAZYLLM_ROOT = os.path.join(_ALGO, 'lazyllm')
if _ALGO not in sys.path:
    sys.path.insert(0, _ALGO)
if _LAZYLLM_ROOT not in sys.path:
    sys.path.insert(0, _LAZYLLM_ROOT)

for _module_name in list(sys.modules):
    if _module_name == 'lazyllm' or _module_name.startswith('lazyllm.'):
        del sys.modules[_module_name]

from chat.tools import vocab as vocab_tool
from vocab import db as vocab_db


def test_resolve_create_user_id_for_timestamped_session(monkeypatch):
    seen_session_ids = []

    class _FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            return self._value

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _sql, params):
            seen_session_ids.append(params['session_id'])
            if params['session_id'] == 'conv-1':
                return _FakeResult('user-1')
            return _FakeResult('')

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    monkeypatch.setattr(vocab_db, '_get_core_conn', lambda db_dsn=None, db_url=None: _FakeEngine())

    assert vocab_db.resolve_create_user_id_for_session('conv-1_1778221345821') == 'user-1'
    assert seen_session_ids == ['conv-1_1778221345821', 'conv-1']


def test_vocab_manage_creates_group_for_new_pair(monkeypatch):
    captured = {}

    monkeypatch.setattr(vocab_tool, '_agentic_config', lambda: {
        'session_id': 'sid-1',
        'create_user_id': 'user-1',
    })
    monkeypatch.setattr(vocab_tool, 'fetch_vocab_groups_for_create_user_id', lambda user_id: {})

    def _fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'persisted': 'core_api'}

    monkeypatch.setattr(vocab_tool, '_post_core_api', _fake_post)

    result = vocab_tool.vocab_manage([
        {'word': '苹果', 'synonym': 'apple', 'reason': 'user explicitly asked to remember it'},
    ])

    assert result['success'] is True
    assert captured['path'] == '/inner/word_group:apply'
    assert captured['payload']['action_list'] == [{
        'reason': 'user explicitly asked to remember it',
        'words': ['苹果', 'apple'],
        'description': '',
        'group_ids': '[]',
        'create_user_id': 'user-1',
        'message_ids': '[]',
        'action': 'create_new_group',
    }]


def test_vocab_manage_resolves_user_from_session_and_adds_to_group(monkeypatch):
    captured = {}

    monkeypatch.setattr(vocab_tool, '_agentic_config', lambda: {'session_id': 'sid-2'})
    monkeypatch.setattr(vocab_tool, 'resolve_create_user_id_for_session', lambda session_id: 'user-2')
    monkeypatch.setattr(vocab_tool, 'fetch_vocab_groups_for_create_user_id', lambda user_id: {
        'g1': {'group_id': 'g1', 'words': ['民法'], 'description': '', 'references': []},
    })

    def _fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'persisted': 'core_api'}

    monkeypatch.setattr(vocab_tool, '_post_core_api', _fake_post)

    result = vocab_tool.vocab_manage([
        {'word': '民法', 'synonym': '民事法律', 'reason': 'user used the terms as the same concept'},
    ])

    assert result['success'] is True
    assert captured['payload']['action_list'] == [{
        'reason': 'user used the terms as the same concept',
        'words': ['民事法律'],
        'description': '',
        'group_ids': '["g1"]',
        'create_user_id': 'user-2',
        'message_ids': '[]',
        'action': 'add_to_group',
    }]