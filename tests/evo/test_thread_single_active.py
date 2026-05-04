from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from evo.service.core import store as _store
from evo.service.threads.hub import ThreadHub, mount


def _make_hub(tmp_path) -> ThreadHub:
    jm = SimpleNamespace(
        config=SimpleNamespace(storage=SimpleNamespace(base_dir=tmp_path)),
        store=_store.FsStateStore(tmp_path / 'state'),
    )
    intents = SimpleNamespace(_base_dir=tmp_path / 'state' / 'intents')
    return ThreadHub(jm=jm, planner=object(), intent_store=intents, ops=object())


def test_create_thread_blocks_second_active_thread_for_same_user(tmp_path):
    hub = _make_hub(tmp_path)

    first = hub.create_thread({'mode': 'interactive'}, user_id='u1', user_name='tester')

    assert first['create_user_id'] == 'u1'
    assert first['create_user_name'] == 'tester'
    with pytest.raises(HTTPException) as exc:
        hub.create_thread({'mode': 'interactive'}, user_id='u1')

    assert exc.value.status_code == 409
    assert exc.value.detail['thread_id'] == first['id']
    assert exc.value.detail['flow_status']['status'] == 'running'


def test_create_thread_allows_different_users(tmp_path):
    hub = _make_hub(tmp_path)

    first = hub.create_thread({'mode': 'interactive'}, user_id='u1')
    second = hub.create_thread({'mode': 'interactive'}, user_id='u2')

    assert first['id'] != second['id']
    assert second['create_user_id'] == 'u2'


def test_create_thread_route_uses_user_headers_for_guard(tmp_path):
    hub = _make_hub(tmp_path)
    app = FastAPI()
    mount(app, hub)
    client = TestClient(app)

    first = client.post('/v1/evo/threads', headers={'X-User-Id': 'u1'}, json={'mode': 'interactive'})
    second = client.post('/v1/evo/threads', headers={'X-User-Id': 'u1'}, json={'mode': 'interactive'})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()['detail']['thread_id'] == first.json()['id']
