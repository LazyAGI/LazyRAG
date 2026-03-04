"""
Unit tests for algorithm/chat/chat.py.
Tests Pydantic models (History, ChatResponse).
Full chat endpoint test requires Document/LLM mocks - run with services up for integration.
"""
import pytest

# Import chat module - may fail if lazyllm/Document init requires external services
try:
    from chat.chat import History, ChatResponse
    CHAT_AVAILABLE = True
except (ImportError, Exception):
    CHAT_AVAILABLE = False


@pytest.mark.skipif(not CHAT_AVAILABLE, reason='chat module or lazyllm not available')
def test_history_model():
    """History model has role and content."""
    h = History(role='user', content='hello')
    assert h.role == 'user'
    assert h.content == 'hello'
    assert h.dict() == {'role': 'user', 'content': 'hello'}


@pytest.mark.skipif(not CHAT_AVAILABLE, reason='chat module or lazyllm not available')
def test_chat_response_schema():
    """ChatResponse has code, msg, data, cost."""
    r = ChatResponse(code=200, msg='ok', data='answer', cost=0.5)
    assert r.code == 200
    assert r.cost == 0.5
    assert r.data == 'answer'
