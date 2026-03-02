import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazyllm.tools.rag import Document, OnlineEmbeddingModule, MineruPDFReader  # noqa: E402
from lazyllm.tools.rag.doc_impl import NodeGroupType  # noqa: E402
from lazyllm.tools.rag.parsing_service import DocumentProcessor  # noqa: E402

store_config = {
    'vector_store': {
        'type': 'milvus',
        'kwargs': {
            'uri': os.getenv('MILVUS_URI', 'http://localhost:19530'),
            'index_kwargs': {
                'index_type': 'FLAT',
                'metric_type': 'COSINE',
            },
        },
    },
    'segment_store': {
        'type': 'opensearch',
        'kwargs': {
            'uris': os.getenv('OPENSEARCH_URI', 'https://localhost:9200'),
            'client_kwargs': {
                'http_compress': True,
                'use_ssl': True,
                'verify_certs': False,
                'user': os.getenv('OPENSEARCH_USER', 'admin'),
                'password': os.getenv('OPENSEARCH_PASSWORD', 'admin'),
            },
        },
    },
}

mineru_url = os.getenv('MINERU_SERVER_URL', 'http://localhost:8000').rstrip('/')
processor_url = os.getenv('DOCUMENT_PROCESSOR_URL', 'http://localhost:8000')
server_port = int(os.getenv('DOCUMENT_SERVER_PORT', '8000'))

docs = Document(
    dataset_path=None,
    name='algo1',
    embed=OnlineEmbeddingModule(),
    store_conf=store_config,
    manager=DocumentProcessor(url=processor_url),
    doc_fields=[],
    server=server_port,
)

docs.add_reader('*.pdf', MineruPDFReader(mineru_url))
docs.create_node_group(
    name='block',
    display_name='段落切片',
    group_type=NodeGroupType.CHUNK,
    transform=lambda x: x,
)
docs.activate_group('block')

if __name__ == '__main__':
    docs.start()
