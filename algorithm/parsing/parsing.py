import os
import time
import urllib.error
import urllib.request

import requests

from lazyllm import OnlineEmbeddingModule
from lazyllm.tools.rag import Document, MineruPDFReader, PDFReader
from lazyllm.tools.rag.doc_impl import NodeGroupType
from lazyllm.tools.rag.parsing_service import DocumentProcessor
from lazyllm.tools.rag.readers import PaddleOCRPDFReader
from lazyllm.tools.rag.transform import SentenceSplitter


ALGO_ID = 'algo1'


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f'{name} is required')
    return value


def _build_store_config():
    milvus_uri = _require_env('LAZYRAG_MILVUS_URI')
    opensearch_uri = _require_env('LAZYRAG_OPENSEARCH_URI')
    return {
        'vector_store': {
            'type': 'milvus',
            'kwargs': {
                'uri': milvus_uri,
                'index_kwargs': {
                    'index_type': 'FLAT',
                    'metric_type': 'COSINE',
                },
            },
        },
        'segment_store': {
            'type': 'opensearch',
            'kwargs': {
                'uris': opensearch_uri,
                'client_kwargs': {
                    'http_compress': True,
                    'use_ssl': True,
                    'verify_certs': False,
                    'user': os.getenv('LAZYRAG_OPENSEARCH_USER', 'admin'),
                    'password': os.getenv('LAZYRAG_OPENSEARCH_PASSWORD', 'admin'),
                },
            },
        },
    }


def _build_pdf_reader():
    ocr_type = os.getenv('LAZYRAG_OCR_SERVER_TYPE', 'none')
    ocr_url = os.getenv('LAZYRAG_OCR_SERVER_URL', 'http://localhost:8000').rstrip('/')
    if ocr_type in ('none', None, ''):
        return PDFReader()
    if ocr_type == 'mineru':
        return MineruPDFReader(ocr_url)
    if ocr_type == 'paddleocr':
        return PaddleOCRPDFReader(url=ocr_url)
    raise ValueError(f'Unsupported LAZYRAG_OCR_SERVER_TYPE: {ocr_type!r}')


def _get_algo_server_port() -> int:
    return int(os.getenv('LAZYRAG_ALGO_SERVER_PORT', os.getenv('LAZYRAG_DOCUMENT_SERVER_PORT', '8000')))


def _wait_for_http_ok(url: str, label: str, timeout: float, interval: float) -> None:
    deadline = time.time() + timeout if timeout > 0 else None
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        if deadline is not None and time.time() >= deadline:
            raise RuntimeError(f'timed out waiting for {label}: {url}')
        time.sleep(interval)


def _wait_for_algorithm_registration(processor_url: str, algo_id: str, timeout: float, interval: float) -> None:
    deadline = time.time() + timeout if timeout > 0 else None
    algo_list_url = f'{processor_url.rstrip("/")}/algo/list'
    while True:
        try:
            response = requests.get(algo_list_url, timeout=3)
            response.raise_for_status()
            data = response.json().get('data', [])
            if any(item.get('algo_id') == algo_id for item in data):
                return
        except Exception:
            pass
        if deadline is not None and time.time() >= deadline:
            raise RuntimeError(f'timed out waiting for algorithm registration: {algo_id}')
        time.sleep(interval)


def build_document() -> Document:
    processor_url = os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000')
    server_port = _get_algo_server_port()

    docs = Document(
        dataset_path=None,
        name=ALGO_ID,
        embed=OnlineEmbeddingModule(),
        store_conf=_build_store_config(),
        manager=DocumentProcessor(url=processor_url),
        doc_fields=[],
        server=server_port,
    )

    docs.add_reader('*.pdf', _build_pdf_reader())
    docs.create_node_group(
        name='block',
        display_name='段落切片',
        group_type=NodeGroupType.CHUNK,
        transform=SentenceSplitter(chunk_size=512, chunk_overlap=50),
    )
    docs.activate_group('block')
    return docs


def main() -> None:
    processor_url = os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000').rstrip('/')
    retry_interval = float(os.getenv('LAZYRAG_STARTUP_RETRY_INTERVAL', '2'))
    startup_timeout = float(os.getenv('LAZYRAG_STARTUP_TIMEOUT', '0'))

    _wait_for_http_ok(f'{processor_url}/health', 'DocumentProcessor', startup_timeout, retry_interval)

    docs = build_document()
    docs.start()

    _wait_for_http_ok(
        f'http://127.0.0.1:{_get_algo_server_port()}/docs',
        'lazyllm-algo local service',
        startup_timeout,
        retry_interval,
    )
    _wait_for_algorithm_registration(processor_url, ALGO_ID, startup_timeout, retry_interval)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
