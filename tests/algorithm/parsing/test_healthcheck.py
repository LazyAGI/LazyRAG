import pytest

import parsing.healthcheck as healthcheck


class _Response:
    def __init__(self, payload=None):
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_ensure_ok_raises_for_bad_status(monkeypatch):
    class BadResponse:
        def raise_for_status(self):
            raise RuntimeError('bad status')

    monkeypatch.setattr(healthcheck.requests, 'get', lambda url, timeout: BadResponse())

    with pytest.raises(RuntimeError, match='bad status'):
        healthcheck._ensure_ok('http://service.test/health')


def test_main_checks_local_docs_and_processor_registration(monkeypatch):
    seen_urls = []

    def fake_get(url, timeout):
        seen_urls.append((url, timeout))
        if url.endswith('/algo/list'):
            return _Response({'data': [{'algo_id': healthcheck.ALGO_ID}]})
        return _Response()

    monkeypatch.setenv('LAZYRAG_ALGO_SERVER_PORT', '18000')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://processor.test/')
    monkeypatch.setattr(healthcheck.requests, 'get', fake_get)

    assert healthcheck.main() == 0
    assert seen_urls == [
        ('http://127.0.0.1:18000/docs', 3),
        ('http://processor.test/algo/list', 3),
    ]


def test_main_uses_document_server_port_fallback(monkeypatch):
    seen_urls = []

    def fake_get(url, timeout):
        seen_urls.append(url)
        return _Response({'data': [{'algo_id': healthcheck.ALGO_ID}]})

    monkeypatch.delenv('LAZYRAG_ALGO_SERVER_PORT', raising=False)
    monkeypatch.setenv('LAZYRAG_DOCUMENT_SERVER_PORT', '18001')
    monkeypatch.setattr(healthcheck.requests, 'get', fake_get)

    assert healthcheck.main() == 0
    assert seen_urls[0] == 'http://127.0.0.1:18001/docs'


def test_main_raises_when_algo_is_not_registered(monkeypatch):
    monkeypatch.setattr(healthcheck.requests, 'get', lambda url, timeout: _Response({'data': []}))

    with pytest.raises(RuntimeError, match='algo_id not registered yet'):
        healthcheck.main()
