from urllib.parse import urlparse

from lazyllm import AutoModel
from lazyllm.tools.rag import Document, MineruPDFReader, PDFReader
from lazyllm.tools.rag.doc_impl import NodeGroupType
from lazyllm.tools.rag.parsing_service import DocumentProcessor
from lazyllm.tools.rag.readers import PaddleOCRPDFReader

from chat.utils.load_config import get_embed_keys, get_embed_index_kwargs, get_config_path
from config import config as _cfg
from parsing.transform import GeneralParser, LineSplitter

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
    patch_applied = _cfg['ocr_patch_applied']
    service_variant = _cfg['ocr_service_variant']
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
            timeout=3600,
            patch_applied=patch_applied,
            service_variant=service_variant,
            image_cache_dir='/app/uploads/.image_cache'
        )
    if ocr_type == 'paddleocr':
        return PaddleOCRPDFReader(
            url=ocr_url,
            service_variant=service_variant,
            images_dir='/app/uploads/.image_cache'
        )
    raise ValueError(f'Unsupported OCR server type: {ocr_type!r}')


def reset_document() -> None:
    '''Drop all vector/segment data and the algorithm registration record.

    Called when LAZYRAG_RESET_ALGO_ON_STARTUP=true so that a fresh rebuild
    starts from a clean state (e.g. after changing the embed model or node groups).
    Operates directly on the underlying stores — does NOT require a started Document.
    TODO(wangzhihong): move it to lazyllm.Document
    '''
    import re
    from lazyllm import LOG
    from lazyllm.tools.rag.store import MilvusStore, OpenSearchStore

    LOG.warning(f'[build_document] RESET_ALGO_ON_STARTUP is set — dropping all data for algo "{ALGO_ID}"')

    # Mirrors _DocumentStore._gen_collection_name: col_{algo}_{group}, lowercased.
    _pat = re.compile(r'[^a-z0-9_]+')

    def _col(group: str) -> str:
        return _pat.sub('_', f'col_{ALGO_ID}_{group}'.lower()).strip('_')

    activated_groups = ['block', 'line', '__lazyllm_root__', '__lazyllm_image__']
    store_conf = _build_store_config(get_embed_index_kwargs())

    milvus_cfg = (store_conf.get('vector_store') or {}).get('kwargs', {})
    opensearch_cfg = (store_conf.get('segment_store') or {}).get('kwargs', {})

    if milvus_cfg.get('uri'):
        milvus = MilvusStore(**{k: v for k, v in milvus_cfg.items() if k != 'index_kwargs'})
        for group in activated_groups:
            milvus.delete(_col(group))
        LOG.warning(f'[build_document] Milvus collections dropped for algo "{ALGO_ID}"')

    if opensearch_cfg.get('uris'):
        opensearch = OpenSearchStore(**opensearch_cfg)
        for group in activated_groups:
            opensearch.delete(_col(group))
        LOG.warning(f'[build_document] OpenSearch indices dropped for algo "{ALGO_ID}"')

    DocumentProcessor(url=_cfg['document_processor_url']).drop_algorithm(ALGO_ID)
    LOG.warning(f'[build_document] Reset complete for algo "{ALGO_ID}"')


def build_document() -> Document:
    processor_url = _cfg['document_processor_url']
    server_port = get_algo_server_port()
    embed_keys = get_embed_keys()
    if not embed_keys:
        raise ValueError('At least one embed role must be configured in the model config.')
    # get_config_path() resolves the 'inner'/'online'/'dynamic' alias to the actual
    # file path that AutoModel's config-map loader (get_module_config_map) expects.
    # Passing the raw alias string (e.g. 'online') causes the loader to treat it as a
    # non-existent file path and return an empty map, so the embed model falls back to
    # an unconfigured OnlineModule instead of the Qwen/BGE model in the yaml.
    resolved_config_path = get_config_path()
    embed = {k: AutoModel(model=k, config=resolved_config_path) for k in embed_keys}

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
