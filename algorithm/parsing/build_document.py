import os
from urllib.parse import urlparse

from lazyllm.tools.rag import Document, MineruPDFReader, PDFReader
from lazyllm.tools.rag.doc_impl import NodeGroupType
from lazyllm.tools.rag.parsing_service import DocumentProcessor
from lazyllm.tools.rag.readers import PaddleOCRPDFReader

from common.model import build_embedding_models, get_runtime_model_settings
from parsing.transform import NodeParser, GeneralParser, LineSplitter

ALGO_ID = 'general_algo'


def _parse_bool_env(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip().lower()
    if value == '':
        return None
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    raise ValueError(f'{name} must be a boolean string, got: {value!r}')


def _default_mineru_upload_mode(ocr_url: str) -> bool:
    hostname = (urlparse(ocr_url).hostname or '').lower()
    # Only the in-network MinerU service can resolve the same container path.
    return hostname != 'mineru'


def get_algo_server_port() -> int:
    return int(os.getenv('LAZYRAG_ALGO_SERVER_PORT', os.getenv('LAZYRAG_DOCUMENT_SERVER_PORT', '8000')))


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f'{name} is required')
    return value


def _build_store_config(index_kwargs):
    milvus_uri = _require_env('LAZYRAG_MILVUS_URI')
    opensearch_uri = _require_env('LAZYRAG_OPENSEARCH_URI')
    return {
        'vector_store': {
            'type': 'milvus',
            'kwargs': {
                'uri': milvus_uri,
                'index_kwargs': index_kwargs,
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
                    'password': os.getenv('LAZYRAG_OPENSEARCH_PASSWORD', 'LazyRAG_OpenSearch123!'),
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
        upload_mode = _parse_bool_env('LAZYRAG_MINERU_UPLOAD_MODE')
        if upload_mode is None:
            upload_mode = _default_mineru_upload_mode(ocr_url)
        return MineruPDFReader(
            url=ocr_url,
            backend=os.getenv('LAZYRAG_MINERU_BACKEND', 'pipeline'),
            upload_mode=upload_mode,
            post_func=NodeParser(),
            timeout=3600
        )
    if ocr_type == 'paddleocr':
        return PaddleOCRPDFReader(url=ocr_url)
    raise ValueError(f'Unsupported LAZYRAG_OCR_SERVER_TYPE: {ocr_type!r}')


def build_document() -> Document:
    processor_url = os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000')
    server_port = get_algo_server_port()
    settings = get_runtime_model_settings()
    embed = build_embedding_models(settings)

    docs = Document(
        dataset_path=None,
        name=ALGO_ID,
        embed=embed,
        store_conf=_build_store_config(settings.index_kwargs),
        manager=DocumentProcessor(url=processor_url),
        doc_fields=[],
        server=server_port,
    )

    docs.add_reader('*.pdf', _build_pdf_reader())
    docs.create_node_group(name='block', display_name='段落切片',
                           group_type=NodeGroupType.CHUNK, transform=GeneralParser(max_length=2048, split_by='\n'))
    docs.create_node_group(name='line', display_name='句子切片',
                           group_type=NodeGroupType.CHUNK, transform=LineSplitter, parent='block')
    docs.activate_group('block', embed_keys=settings.embed_keys)
    docs.activate_group('line', embed_keys=settings.embed_keys)
    return docs
