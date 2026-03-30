"""
Unit tests for algorithm/chat/chat.py.
Tests Pydantic models (History, ChatResponse) and chat endpoint body validation.
Full chat endpoint test requires Document/LLM mocks - run with services up for integration.
"""
import pytest

try:
    from chat.chat import History, ChatResponse, _normalize_history
    CHAT_AVAILABLE = True
except ImportError:
    CHAT_AVAILABLE = False


@pytest.mark.skipif(not CHAT_AVAILABLE, reason='chat module or lazyllm not available')
def test_history_model():
    """History model has role and content."""
    h = History(role='user', content='hello')
    assert h.role == 'user'
    assert h.content == 'hello'
    dump = getattr(h, 'model_dump', h.dict)()
    assert dump == {'role': 'user', 'content': 'hello'}


@pytest.mark.skipif(not CHAT_AVAILABLE, reason='chat module or lazyllm not available')
def test_chat_response_schema():
    """ChatResponse has code, msg, data, cost."""
    r = ChatResponse(code=200, msg='ok', data='answer', cost=0.5)
    assert r.code == 200
    assert r.cost == 0.5
    assert r.data == 'answer'


@pytest.mark.skipif(not CHAT_AVAILABLE, reason='chat module or lazyllm not available')
def test_normalize_history_accepts_empty_dict():
    """Frontend/proxy may send history as {}; must normalize to [] (no 422)."""
    assert _normalize_history({}) == []
    assert _normalize_history(None) == []
    assert _normalize_history([]) == []
    out = _normalize_history([{'role': 'user', 'content': 'hi'}])
    assert len(out) == 1 and out[0].role == 'user' and out[0].content == 'hi'


@pytest.mark.skipif(not CHAT_AVAILABLE, reason='chat module or lazyllm not available')
def test_chat_endpoint_accepts_history_as_object():
    """Simulate frontend request where history is {} (e.g. after Kong proxy). No 422."""
    from fastapi.testclient import TestClient
    from chat.chat import app
    client = TestClient(app)
    body = {
        'query': 'hello',
        'history': {},
        'session_id': 'web-123',
        'filters': None,
        'files': None,
    }
    response = client.post('/api/chat', json=body)
    assert response.status_code != 422, (
        f'Chat must accept history={{}}; got 422: {response.json()}'
    )
    if response.status_code == 422:
        data = response.json()
        assert 'history' not in str(data.get('detail', [])), (
            f'Validation error should not mention history: {data}'
        )
