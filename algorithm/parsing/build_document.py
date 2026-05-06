from urllib.parse import urlparse

from lazyllm import AutoModel
from lazyllm.tools.rag import Document, MineruPDFReader, PDFReader
from lazyllm.tools.rag.doc_impl import NodeGroupType
from lazyllm.tools.rag.parsing_service import DocumentProcessor
from lazyllm.tools.rag.readers import PaddleOCRPDFReader

from chat.utils.load_config import get_embed_keys, get_embed_index_kwargs
from config import config as _cfg
from parsing.transform import NodeParser, GeneralParser, LineSplitter

ALGO_ID = 'general_algo'


def _parse_bool_config(value: str | None) -> bool | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value == '':
        return None
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    raise ValueError(f'mineru_upload_mode must be a boolean string, got: {value!r}')


def _default_mineru_upload_mode(ocr_url: str) -> bool:
    hostname = (urlparse(ocr_url).hostname or '').lower()
    # Only the in-network MinerU service can resolve the same container path.
    return hostname != 'mineru'


def get_algo_server_port() -> int:
    port = _cfg['algo_server_port']
    if port:
        return port
    return _cfg['document_server_port']


def _build_store_config(index_kwargs):
    milvus_uri = _cfg['milvus_uri']
    if not milvus_uri:
        raise ValueError('LAZYRAG_MILVUS_URI is required')
    opensearch_uri = _cfg['opensearch_uri']
    if not opensearch_uri:
        raise ValueError('LAZYRAG_OPENSEARCH_URI is required')
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
                    'user': _cfg['opensearch_user'],
                    'password': _cfg['opensearch_password'] or 'LazyRAG_OpenSearch123!',
                },
            },
        },
    }


def _build_pdf_reader():
    ocr_type = _cfg['ocr_server_type']
    ocr_url = _cfg['ocr_server_url'].rstrip('/')
    if ocr_type in ('none', None, ''):
        return PDFReader()
    if ocr_type == 'mineru':
        upload_mode = _parse_bool_config(_cfg['mineru_upload_mode'])
        if upload_mode is None:
            upload_mode = _default_mineru_upload_mode(ocr_url)
        return MineruPDFReader(
            url=ocr_url,
            backend=_cfg['mineru_backend'],
            upload_mode=upload_mode,
            post_func=NodeParser(),
            timeout=3600
        )
    if ocr_type == 'paddleocr':
        return PaddleOCRPDFReader(url=ocr_url)
    raise ValueError(f'Unsupported OCR server type: {ocr_type!r}')


def build_document() -> Document:
    processor_url = _cfg['document_processor_url']
    server_port = get_algo_server_port()
    embed_keys = get_embed_keys()
    if not embed_keys:
        raise ValueError('At least one embed role must be configured in the model config.')
    embed = {k: AutoModel(model=k, config=True) for k in embed_keys}

    docs = Document(
        dataset_path=None,
        name=ALGO_ID,
        embed=embed,
        store_conf=_build_store_config(get_embed_index_kwargs()),
        manager=DocumentProcessor(url=processor_url),
        doc_fields=[],
        server=server_port,
    )

    docs.add_reader('*.pdf', _build_pdf_reader())
    docs.create_node_group(name='block', display_name='paragraph slice',
                           group_type=NodeGroupType.CHUNK, transform=GeneralParser(max_length=2048, split_by='\n'))
    docs.create_node_group(name='line', display_name='sentence slice',
                           group_type=NodeGroupType.CHUNK, transform=LineSplitter, parent='block')
    docs.activate_group('block', embed_keys=embed_keys)
    docs.activate_group('line', embed_keys=embed_keys)
    return docs
