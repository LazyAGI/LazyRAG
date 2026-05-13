import types
from datetime import date

import pytest
from pydantic import ValidationError

from chat.components.process.multiturn_query_rewriter import (
    MultiturnQueryRewriter,
    RewriterInput,
)


def test_rewriter_input_validates_history_and_dates():
    data = RewriterInput(
        chat_history=[{'role': 'user', 'content': '介绍 LazyRAG'}],
        last_user_query='它支持图片吗？',
        current_date=date(2026, 4, 16),
        has_appendix=False,
    )

    assert data.chat_history[0].role == 'user'
    assert data.current_date.isoformat() == '2026-04-16'

    with pytest.raises(ValidationError):
        RewriterInput(
            chat_history=[{'role': 'invalid', 'content': 'bad'}],
            last_user_query='bad',
            current_date=date(2026, 4, 16),
        )


def test_multiturn_query_rewriter_updates_query_when_llm_returns_json(monkeypatch):
    captured = {}

    class FakeSharedLLM:
        def __call__(self, payload, **kwargs):
            captured['payload'] = payload
            captured['kwargs'] = kwargs
            return {'rewritten_query': 'LazyRAG 是否支持图片检索？'}

    class FakeLLM:
        def share(self, **kwargs):
            captured['share_kwargs'] = kwargs
            return FakeSharedLLM()

    monkeypatch.setattr(
        'chat.components.process.multiturn_query_rewriter.date',
        types.SimpleNamespace(today=lambda: date(2026, 4, 16)),
    )
    rewriter = MultiturnQueryRewriter(FakeLLM())
    user_input = {'query': '它支持图片吗？', 'history': [{'role': 'user', 'content': '介绍 LazyRAG'}]}

    result = rewriter.forward(user_input, temperature=0)

    assert result['query'] == 'LazyRAG 是否支持图片检索？'
    assert result['origin_query'] == '它支持图片吗？'
    assert '"current_date":"2026-04-16"' in captured['payload']
    assert captured['share_kwargs']['stream'] is False
    assert captured['kwargs'] == {'temperature': 0}


def test_multiturn_query_rewriter_keeps_query_when_llm_response_is_not_dict(monkeypatch):
    class FakeSharedLLM:
        def __call__(self, payload, **kwargs):
            return 'not-json'

    class FakeLLM:
        def share(self, **kwargs):
            return FakeSharedLLM()

    monkeypatch.setattr(
        'chat.components.process.multiturn_query_rewriter.date',
        types.SimpleNamespace(today=lambda: date(2026, 4, 16)),
    )
    rewriter = MultiturnQueryRewriter(FakeLLM())
    user_input = {'query': '原问题', 'history': []}

    assert rewriter.forward(user_input) == {'query': '原问题', 'history': []}
