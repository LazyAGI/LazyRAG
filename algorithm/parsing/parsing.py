import os

from lazyllm import OnlineEmbeddingModule
from lazyllm.tools.rag import Document, MineruPDFReader, PDFReader
from lazyllm.tools.rag.readers import PaddleOCRPDFReader
from lazyllm.tools.rag.doc_impl import NodeGroupType
from lazyllm.tools.rag.parsing_service import DocumentProcessor


def _parse_bool_env(name: str, default: bool = True) -> bool:
    """Use allowlist: only 1, true, yes, on enable; anything else (0, false, no, off, not) disables."""
    val = os.getenv(name, '1' if default else '0').lower().strip()
    return val in ('1', 'true', 'yes', 'on')


use_milvus_opensearch = _parse_bool_env('LAZYRAG_USE_MILVUS_OPENSEARCH', default=True)


if use_milvus_opensearch:
    milvus_uri = os.getenv('LAZYRAG_MILVUS_URI')
    opensearch_uri = os.getenv('LAZYRAG_OPENSEARCH_URI')
    if not milvus_uri:
        raise ValueError('LAZYRAG_MILVUS_URI is required')
    if not opensearch_uri:
        raise ValueError('LAZYRAG_OPENSEARCH_URI is required')
    store_config = {
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
else:
    store_config = {'type': 'map', 'kwargs': {}}

ocr_type = os.getenv('LAZYRAG_OCR_SERVER_TYPE', 'none')
ocr_url = os.getenv('LAZYRAG_OCR_SERVER_URL', 'http://localhost:8000').rstrip('/')
processor_url = os.getenv('LAZYRAG_DOCUMENT_PROCESSOR_URL', 'http://localhost:8000')
server_port = int(os.getenv('LAZYRAG_DOCUMENT_SERVER_PORT', '8000'))

if ocr_type in ('none', None, ''):
    pdf_reader = PDFReader()
elif ocr_type == 'mineru':
    pdf_reader = MineruPDFReader(ocr_url)
elif ocr_type == 'paddleocr':
    pdf_reader = PaddleOCRPDFReader(url=ocr_url)
else:
    raise ValueError(f'Unsupported LAZYRAG_OCR_SERVER_TYPE: {ocr_type!r}')

docs = Document(
    dataset_path=None,
    name='algo1',
    embed=OnlineEmbeddingModule(),
    store_conf=store_config,
    manager=DocumentProcessor(url=processor_url),
    doc_fields=[],
    server=server_port,
)

docs.add_reader('*.pdf', pdf_reader)
docs.create_node_group(
    name='block',
    display_name='段落切片',
    group_type=NodeGroupType.CHUNK,
    transform=lambda x: x,
)
docs.activate_group('block')

if __name__ == '__main__':
    docs.start()
    docs._manager._manager.wait()
