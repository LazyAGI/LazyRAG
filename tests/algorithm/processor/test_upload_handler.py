import asyncio
import importlib
import sys
from pathlib import Path

import pytest


class _FakeUploadFile:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


class _FakeRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeAsyncClient:
    response = _FakeResponse(payload={'data': {'task_id': 'task-1'}})
    posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, timeout):
        self.__class__.posts.append({'url': url, 'json': json, 'timeout': timeout})
        return self.__class__.response


def _fresh_import_upload_handler(monkeypatch, tmp_path):
    monkeypatch.setenv('LAZYRAG_UPLOAD_DIR', str(tmp_path))
    monkeypatch.setenv('LAZYRAG_DEFAULT_ALGO_ID', 'default-algo')
    monkeypatch.setenv('LAZYRAG_DEFAULT_GROUP', 'default-group')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_PROCESSOR_PORT', '18000')
    sys.modules.pop('processor.upload_handler', None)
    return importlib.import_module('processor.upload_handler')


def test_upload_and_add_saves_files_and_posts_add_doc_request(monkeypatch, tmp_path):
    module = _fresh_import_upload_handler(monkeypatch, tmp_path)
    _FakeAsyncClient.posts = []
    _FakeAsyncClient.response = _FakeResponse(payload={'data': {'task_id': 'task-1'}})
    monkeypatch.setattr(module.httpx, 'AsyncClient', _FakeAsyncClient)
    monkeypatch.setattr(module, 'gen_docid', lambda path: 'doc-' + Path(path).name)

    response = asyncio.run(
        module.upload_and_add(
            _FakeRequest({'group_name': 'query-group', 'algo_id': 'query-algo', 'override': 'false'}),
            [_FakeUploadFile('a.txt', b'alpha')],
            group_name=None,
            algo_id=None,
            override=None,
        )
    )

    saved_file = next(tmp_path.glob('*/a.txt'))
    assert saved_file.read_bytes() == b'alpha'
    assert response.code == 200
    assert response.data == {'task_id': 'task-1', 'ids': ['doc-a.txt']}
    assert _FakeAsyncClient.posts[0]['url'] == 'http://127.0.0.1:18000/doc/add'
    assert _FakeAsyncClient.posts[0]['json']['algo_id'] == 'query-algo'
    assert _FakeAsyncClient.posts[0]['json']['file_infos'][0]['metadata'] == {'kb_id': 'query-group'}


def test_upload_and_add_uses_form_values_before_query_params(monkeypatch, tmp_path):
    module = _fresh_import_upload_handler(monkeypatch, tmp_path)
    _FakeAsyncClient.posts = []
    _FakeAsyncClient.response = _FakeResponse(payload={'data': {'task_id': 'task-2'}})
    monkeypatch.setattr(module.httpx, 'AsyncClient', _FakeAsyncClient)
    monkeypatch.setattr(module, 'gen_docid', lambda path: 'fixed-doc-id')

    response = asyncio.run(
        module.upload_and_add(
            _FakeRequest({'group_name': 'query-group', 'algo_id': 'query-algo'}),
            [_FakeUploadFile('b.txt', b'beta')],
            group_name='form-group',
            algo_id='form-algo',
            override=None,
        )
    )

    assert response.data == {'task_id': 'task-2', 'ids': ['fixed-doc-id']}
    assert _FakeAsyncClient.posts[0]['json']['algo_id'] == 'form-algo'
    assert _FakeAsyncClient.posts[0]['json']['file_infos'][0]['metadata'] == {'kb_id': 'form-group'}


def test_upload_and_add_rejects_missing_files(monkeypatch, tmp_path):
    module = _fresh_import_upload_handler(monkeypatch, tmp_path)

    with pytest.raises(module.fastapi.HTTPException) as exc_info:
        asyncio.run(module.upload_and_add(_FakeRequest(), [], group_name=None, algo_id=None, override=None))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'files is required'


def test_upload_and_add_forwards_processor_error(monkeypatch, tmp_path):
    module = _fresh_import_upload_handler(monkeypatch, tmp_path)
    _FakeAsyncClient.posts = []
    _FakeAsyncClient.response = _FakeResponse(status_code=503, payload={'detail': 'processor unavailable'})
    monkeypatch.setattr(module.httpx, 'AsyncClient', _FakeAsyncClient)

    with pytest.raises(module.fastapi.HTTPException) as exc_info:
        asyncio.run(
            module.upload_and_add(
                _FakeRequest(),
                [_FakeUploadFile('c.txt', b'gamma')],
                group_name=None,
                algo_id=None,
                override=None,
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == 'processor unavailable'


def test_upload_and_add_cleans_saved_files_on_unexpected_error(monkeypatch, tmp_path):
    module = _fresh_import_upload_handler(monkeypatch, tmp_path)

    class _FailingAsyncClient(_FakeAsyncClient):
        async def post(self, url, json, timeout):
            raise RuntimeError('network down')

    monkeypatch.setattr(module.httpx, 'AsyncClient', _FailingAsyncClient)

    with pytest.raises(module.fastapi.HTTPException) as exc_info:
        asyncio.run(
            module.upload_and_add(
                _FakeRequest(),
                [_FakeUploadFile('d.txt', b'delta')],
                group_name=None,
                algo_id=None,
                override=None,
            )
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'network down'
    assert list(tmp_path.rglob('d.txt')) == []
