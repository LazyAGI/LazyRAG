from types import SimpleNamespace

import pytest

import parsing.build_document as build_document


def test_parse_bool_env_accepts_common_values(monkeypatch):
    monkeypatch.delenv('BOOL_ENV', raising=False)
    assert build_document._parse_bool_env('BOOL_ENV') is None
    monkeypatch.setenv('BOOL_ENV', '  ')
    assert build_document._parse_bool_env('BOOL_ENV') is None
    for value in ['1', 'true', 'yes', 'on']:
        monkeypatch.setenv('BOOL_ENV', value)
        assert build_document._parse_bool_env('BOOL_ENV') is True
    for value in ['0', 'false', 'no', 'off']:
        monkeypatch.setenv('BOOL_ENV', value)
        assert build_document._parse_bool_env('BOOL_ENV') is False


def test_parse_bool_env_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv('BOOL_ENV', 'maybe')

    with pytest.raises(ValueError, match='BOOL_ENV must be a boolean string'):
        build_document._parse_bool_env('BOOL_ENV')


def test_default_mineru_upload_mode_only_disables_container_hostname(monkeypatch):
    assert build_document._default_mineru_upload_mode('http://mineru:8000') is False
    assert build_document._default_mineru_upload_mode('http://localhost:8000') is True
    assert build_document._default_mineru_upload_mode('https://ocr.example.test') is True


def test_get_algo_server_port_prefers_algo_port(monkeypatch):
    monkeypatch.delenv('LAZYRAG_ALGO_SERVER_PORT', raising=False)
    monkeypatch.delenv('LAZYRAG_DOCUMENT_SERVER_PORT', raising=False)
    assert build_document.get_algo_server_port() == 8000
    monkeypatch.setenv('LAZYRAG_DOCUMENT_SERVER_PORT', '18001')
    assert build_document.get_algo_server_port() == 18001
    monkeypatch.setenv('LAZYRAG_ALGO_SERVER_PORT', '18002')
    assert build_document.get_algo_server_port() == 18002


def test_build_store_config_reads_required_and_optional_env(monkeypatch):
    monkeypatch.setenv('LAZYRAG_MILVUS_URI', 'http://milvus.test')
    monkeypatch.setenv('LAZYRAG_OPENSEARCH_URI', 'https://opensearch.test')
    monkeypatch.setenv('LAZYRAG_OPENSEARCH_USER', 'user')
    monkeypatch.setenv('LAZYRAG_OPENSEARCH_PASSWORD', 'pass')

    config = build_document._build_store_config({'index': 'flat'})

    assert config['vector_store']['kwargs']['uri'] == 'http://milvus.test'
    assert config['vector_store']['kwargs']['index_kwargs'] == {'index': 'flat'}
    assert config['segment_store']['kwargs']['uris'] == 'https://opensearch.test'
    assert config['segment_store']['kwargs']['client_kwargs']['user'] == 'user'
    assert config['segment_store']['kwargs']['client_kwargs']['password'] == 'pass'


def test_require_env_raises_for_missing_value(monkeypatch):
    monkeypatch.delenv('MISSING_REQUIRED_ENV', raising=False)

    with pytest.raises(ValueError, match='MISSING_REQUIRED_ENV is required'):
        build_document._require_env('MISSING_REQUIRED_ENV')


def test_build_pdf_reader_selects_plain_pdf_reader(monkeypatch):
    class FakePDFReader:
        pass

    monkeypatch.setattr(build_document, 'PDFReader', FakePDFReader)
    monkeypatch.setenv('LAZYRAG_OCR_SERVER_TYPE', 'none')

    assert isinstance(build_document._build_pdf_reader(), FakePDFReader)


def test_build_pdf_reader_selects_mineru_with_upload_mode(monkeypatch):
    seen = {}

    class FakeMineruPDFReader:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(build_document, 'MineruPDFReader', FakeMineruPDFReader)
    monkeypatch.setenv('LAZYRAG_OCR_SERVER_TYPE', 'mineru')
    monkeypatch.setenv('LAZYRAG_OCR_SERVER_URL', 'http://mineru:8000/')
    monkeypatch.delenv('LAZYRAG_MINERU_UPLOAD_MODE', raising=False)

    reader = build_document._build_pdf_reader()

    assert isinstance(reader, FakeMineruPDFReader)
    assert seen['url'] == 'http://mineru:8000'
    assert seen['backend'] == 'pipeline'
    assert seen['upload_mode'] is False
    assert isinstance(seen['post_func'], build_document.NodeParser)
    assert seen['timeout'] == 3600


def test_build_pdf_reader_selects_paddleocr(monkeypatch):
    seen = {}

    class FakePaddleOCRPDFReader:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(build_document, 'PaddleOCRPDFReader', FakePaddleOCRPDFReader)
    monkeypatch.setenv('LAZYRAG_OCR_SERVER_TYPE', 'paddleocr')
    monkeypatch.setenv('LAZYRAG_OCR_SERVER_URL', 'http://paddle.test/')

    assert isinstance(build_document._build_pdf_reader(), FakePaddleOCRPDFReader)
    assert seen == {'url': 'http://paddle.test'}


def test_build_pdf_reader_rejects_unknown_ocr_type(monkeypatch):
    monkeypatch.setenv('LAZYRAG_OCR_SERVER_TYPE', 'unknown')

    with pytest.raises(ValueError, match='Unsupported LAZYRAG_OCR_SERVER_TYPE'):
        build_document._build_pdf_reader()


def test_build_document_wires_readers_groups_and_embeddings(monkeypatch):
    class FakeDocumentProcessor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeDocument:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.readers = []
            self.node_groups = []
            self.activated = []

        def add_reader(self, pattern, reader):
            self.readers.append((pattern, reader))

        def create_node_group(self, **kwargs):
            self.node_groups.append(kwargs)

        def activate_group(self, name, embed_keys):
            self.activated.append((name, embed_keys))

    settings = SimpleNamespace(embed_keys=['dense', 'sparse'], index_kwargs={'nlist': 16})
    monkeypatch.setattr(build_document, 'Document', FakeDocument)
    monkeypatch.setattr(build_document, 'DocumentProcessor', FakeDocumentProcessor)
    monkeypatch.setattr(build_document, 'get_retrieval_settings', lambda: settings)
    monkeypatch.setattr(build_document, 'get_automodel', lambda key: f'emb-{key}')
    monkeypatch.setattr(build_document, '_build_store_config', lambda index_kwargs: {'index_kwargs': index_kwargs})
    monkeypatch.setattr(build_document, '_build_pdf_reader', lambda: 'pdf-reader')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://processor.test')
    monkeypatch.setenv('LAZYRAG_ALGO_SERVER_PORT', '18003')

    docs = build_document.build_document()

    assert docs.kwargs['name'] == build_document.ALGO_ID
    assert docs.kwargs['embed'] == {'dense': 'emb-dense', 'sparse': 'emb-sparse'}
    assert docs.kwargs['store_conf'] == {'index_kwargs': {'nlist': 16}}
    assert docs.kwargs['manager'].kwargs == {'url': 'http://processor.test'}
    assert docs.kwargs['server'] == 18003
    assert docs.readers == [('*.pdf', 'pdf-reader')]
    assert [group['name'] for group in docs.node_groups] == ['block', 'line']
    assert 'parent' not in docs.node_groups[0]
    assert docs.node_groups[1]['parent'] == 'block'
    assert docs.activated == [('block', ['dense', 'sparse']), ('line', ['dense', 'sparse'])]
