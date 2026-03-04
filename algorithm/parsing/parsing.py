import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

milvus_uri = os.getenv('LAZYRAG_MILVUS_URI')
opensearch_uri = os.getenv('LAZYRAG_OPENSEARCH_URI')
if not milvus_uri:
    raise ValueError('LAZYRAG_MILVUS_URI is required')
if not opensearch_uri:
    raise ValueError('LAZYRAG_OPENSEARCH_URI is required')

from lazyllm.tools.rag import Document, OnlineEmbeddingModule, MineruPDFReader, PDFReader  # noqa: E402
from lazyllm.tools.rag.readers import PaddleOCRPDFReader  # noqa: E402
from lazyllm.tools.rag.doc_impl import NodeGroupType  # noqa: E402
from lazyllm.tools.rag.parsing_service import DocumentProcessor  # noqa: E402

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
