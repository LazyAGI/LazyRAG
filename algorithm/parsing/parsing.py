from lazyllm.tools.rag import Document, OnlineEmbeddingModule, DocumentProcessor, NodeGroupType
from lazyllm.tools.rag.reader import MinerUPdfReader
import os


store_config = {
    'vector_store': {
        'type': 'milvus',
        'kwargs': {
            'uri': os.getenv('MILVUS_URI', 'http://localhost:19530'),
            'index_kwargs':{
                'index_type': 'FLAT',
                'metric_type': 'COSINE'
            }
        }
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
            }
        }
    }
}


docs = Document(dataset_path=None, name='algo1', 
    embed=OnlineEmbeddingModule(), store_conf=store_config,
    manager=DocumentProcessor(url=os.getenv('DOCUMENT_PROCESSOR_URL', 'http://localhost:8000')),
    doc_fields=[], server=int(os.getenv('DOCUMENT_SERVER_PORT', '8000')))


docs.add_reader("*.pdf", MinerUPdfReader())
docs.create_node_group(name='block', display_name='段落切片', group_type=NodeGroupType.CHUNK, transform=lambda x:x)
docs.activate_group("block")


if __name__ == "__main__":
    docs.start()
