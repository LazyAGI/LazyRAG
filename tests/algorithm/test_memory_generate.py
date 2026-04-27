import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from chat.pipelines.memory_generate import (
    BadRequestError,
    _format_inputs_block,
    generate_memory_content,
)


def _load_memory_generate_routes_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / 'algorithm/chat/app/api/memory_generate_routes.py'
    )
    spec = importlib.util.spec_from_file_location('test_memory_generate_routes', module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.GeneratePayload.model_rebuild()
    return module


def test_format_inputs_block_includes_only_suggestions_when_user_instruct_missing():
    block = _format_inputs_block(
        content='old content',
        suggestions=[{'title': 't', 'content': 'c'}],
        user_instruct=None,
    )

    assert '2) suggestions' in block
    assert '3) user_instruct' not in block


def test_format_inputs_block_includes_only_user_instruct_when_suggestions_missing():
    block = _format_inputs_block(
        content='old content',
        suggestions=[],
        user_instruct='rewrite this',
    )

    assert '2) user_instruct' in block
    assert '2) suggestions' not in block


def test_generate_memory_content_requires_suggestions_or_user_instruct():
    try:
        generate_memory_content(
            memory_type='memory',
            content='old content',
            suggestions=[],
            user_instruct='  ',
        )
    except BadRequestError as exc:
        assert "At least one of 'suggestions' or 'user_instruct' must be provided." == str(exc)
    else:
        raise AssertionError('Expected BadRequestError')


def test_memory_generate_route_accepts_suggestions_without_user_instruct(monkeypatch):
    memory_generate_routes = _load_memory_generate_routes_module()
    app = FastAPI()
    app.include_router(memory_generate_routes.router)
    client = TestClient(app)

    def fake_generate_memory_content(**kwargs):
        assert kwargs['suggestions'] == [{
            'title': 'Update',
            'content': 'Apply change',
            'reason': None,
            'outdated': None,
        }]
        assert kwargs['user_instruct'] is None
        return 'new content'

    monkeypatch.setattr(
        memory_generate_routes,
        'generate_memory_content',
        fake_generate_memory_content,
    )

    response = client.post(
        '/api/chat/memory/generate',
        json={
            'content': 'old content',
            'suggestions': [{'title': 'Update', 'content': 'Apply change'}],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'code': 0,
        'msg': 'ok',
        'data': {'content': 'new content'},
    }


def test_memory_generate_route_rejects_missing_suggestions_and_user_instruct():
    memory_generate_routes = _load_memory_generate_routes_module()
    app = FastAPI()
    app.include_router(memory_generate_routes.router)
    client = TestClient(app)

    response = client.post(
        '/api/chat/memory/generate',
        json={'content': 'old content'},
    )

    assert response.status_code == 422
