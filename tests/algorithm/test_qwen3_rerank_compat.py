from typing import Any, Dict, List

from chat.components.tmp import local_models as reranker_module
from chat.components.tmp.local_models import Qwen3Rerank
from lazyllm.tools.rag.doc_node import DocNode


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self._payload


def _build_reranker() -> Qwen3Rerank:
    return Qwen3Rerank(embed_url='http://example.com/rerank', api_key='test-key')


def test_qwen3_rerank_supports_query_documents_signature(monkeypatch):
    reranker = _build_reranker()
    seen_payloads: List[Dict[str, Any]] = []

    def _fake_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: Any):
        seen_payloads.append({'url': url, 'json': json, 'headers': headers, 'timeout': timeout})
        return _FakeResponse({
            'results': [
                {'index': 0, 'relevance_score': 0.2},
                {'index': 1, 'relevance_score': 0.9},
                {'index': 2, 'relevance_score': 0.4},
            ]
        })

    monkeypatch.setattr(reranker._session, 'post', _fake_post)

    results = reranker.forward('who wrote this?', documents=['doc-a', 'doc-b', 'doc-c'], top_n=2)

    assert results == [(1, 0.9), (2, 0.4)]
    assert seen_payloads[0]['url'] == 'http://example.com/rerank'
    assert 'who wrote this?' in seen_payloads[0]['json']['query']
    assert 'top_n' not in seen_payloads[0]['json']


def test_qwen3_rerank_supports_keyword_only_documents_signature(monkeypatch):
    reranker = _build_reranker()

    def _fake_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: Any):
        return _FakeResponse({
            'results': [
                {'index': 0, 'relevance_score': 0.3},
                {'index': 1, 'relevance_score': 0.7},
            ]
        })

    monkeypatch.setattr(reranker._session, 'post', _fake_post)

    results = reranker.forward(query='who wrote this?', documents=['doc-a', 'doc-b'], top_n=1)

    assert results == [(1, 0.7)]


def test_qwen3_rerank_supports_documents_query_signature(monkeypatch):
    reranker = _build_reranker()

    def _fake_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: Any):
        return _FakeResponse({
            'results': [
                {'index': 0, 'relevance_score': 0.6},
                {'index': 1, 'relevance_score': 0.1},
            ]
        })

    monkeypatch.setattr(reranker._session, 'post', _fake_post)

    results = reranker.forward(['doc-a', 'doc-b'], query='find a', top_n=1)

    assert results == [(0, 0.6)]


def test_qwen3_rerank_warns_on_empty_query(monkeypatch):
    reranker = _build_reranker()
    warnings = []

    def _fake_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: Any):
        return _FakeResponse({'results': [{'index': 0, 'relevance_score': 0.5}]})

    def _fake_warning(message: str, *args: Any):
        warnings.append(message % args if args else message)

    monkeypatch.setattr(reranker._session, 'post', _fake_post)
    monkeypatch.setattr(reranker_module.LOG, 'warning', _fake_warning)

    results = reranker.forward(['doc-a'], top_n=1)

    assert results == [(0, 0.5)]
    assert any('empty query' in item for item in warnings)


def test_qwen3_rerank_returns_empty_for_empty_documents():
    reranker = _build_reranker()

    assert reranker.forward('query', documents=[]) == []
    assert reranker.forward([], query='query') == []
    assert reranker.forward(query='query', documents=[]) == []


def test_qwen3_rerank_preserves_legacy_nodes_signature(monkeypatch):
    reranker = _build_reranker()

    def _fake_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: Any):
        return _FakeResponse({
            'results': [
                {'index': 0, 'relevance_score': 0.1},
                {'index': 1, 'relevance_score': 0.8},
                {'index': 2, 'relevance_score': 0.3},
            ]
        })

    monkeypatch.setattr(reranker._session, 'post', _fake_post)
    nodes = [DocNode(text='first'), DocNode(text='second'), DocNode(text='third')]

    results = reranker.forward(nodes, query='pick the best one', topk=2)

    assert [node.text for node in results] == ['second', 'third']
    assert results[0].relevance_score == 0.8


def test_qwen3_rerank_respects_zero_topn(monkeypatch):
    reranker = _build_reranker()

    def _fake_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: Any):
        return _FakeResponse({
            'results': [
                {'index': 0, 'relevance_score': 0.1},
                {'index': 1, 'relevance_score': 0.9},
            ]
        })

    monkeypatch.setattr(reranker._session, 'post', _fake_post)
    nodes = [DocNode(text='first'), DocNode(text='second')]

    assert reranker.forward('query', documents=['doc-a', 'doc-b'], top_n=0) == []
    assert reranker.forward(nodes, query='query', topk=0) == []
