import os
import asyncio
import atexit
import functools
import hashlib
import re
import shutil
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

import requests
import yaml
import lazyllm
from lazyllm import AutoModel
from lazyllm.tools.rag import Document, MineruPDFReader, PDFReader
from lazyllm.tools.rag.doc_impl import NodeGroupType
from lazyllm.tools.rag.parsing_service import DocumentProcessor
from lazyllm.tools.rag.readers import PaddleOCRPDFReader
from lazyllm import AutoModel, ModuleBase
from lazyllm.components.formatter import FormatterBase
from lazyllm.components.prompter import PrompterBase

from chat.utils.load_config import get_embed_keys, get_embed_index_kwargs, get_config_path
from config import config as _cfg
from parsing.transform import GeneralParser, LineSplitter

ALGO_ID = 'general_algo'
_RUNTIME_AUTO_MODEL_DIR = Path(tempfile.gettempdir()) / 'lazyrag-runtime-auto-model'
_DEFAULT_LLM_KW: Dict[str, Any] = {
    'temperature': 0.01,
    'max_tokens': 4096,
    'frequency_penalty': 0,
}
_lock = threading.RLock()
_base_models: Dict[str, Any] = {}
_wrapped_models: Dict[str, Any] = {}


def _cleanup_runtime_auto_model_dir() -> None:
    shutil.rmtree(_RUNTIME_AUTO_MODEL_DIR, ignore_errors=True)


atexit.register(_cleanup_runtime_auto_model_dir)


class _StreamingLlmModule(ModuleBase):
    def __init__(self, llm: Any, return_trace: bool = False):
        super().__init__(return_trace=return_trace)
        self.llm = llm

    @property
    def series(self):
        return 'LlmComponent'

    @property
    def type(self):
        return 'LLM'

    def share(self, prompt: PrompterBase = None, format: FormatterBase = None,
              stream: Optional[bool] = None, history: List[List[str]] = None,
              copy_static_params: bool = False):
        self.llm = self.llm.share(
            prompt=prompt, format=format, stream=stream,
            history=history, copy_static_params=copy_static_params,
        )
        return self

    async def _astream(self, text, llm, files, history, **kw):
        with lazyllm.ThreadPoolExecutor(1) as executor:
            future = executor.submit(
                llm, text,
                llm_chat_history=history,
                lazyllm_files=files,
                stream_output=True,
                **kw,
            )
            while True:
                if value := lazyllm.FileSystemQueue().dequeue():
                    yield ''.join(value)
                elif future.done():
                    break
                else:
                    await asyncio.sleep(0.1)

    def forward(self, query, files=None, stream=True, **kwargs: Any) -> Any:
        llm = None
        try:
            lazyllm.LOG.info(f'MODEL_NAME: {self.llm._model_name} GOT QUERY: {query}')
            files = files[:2] if files else None
            hist = kwargs.pop('llm_chat_history', [])
            priority = kwargs.pop('priority', 0)
            strat = kwargs.get('llm_strategy')
            raw = {**_DEFAULT_LLM_KW, 'priority': priority} if strat is None else dict(strat)
            kw = {k: v for k, v in raw.items() if v is not None}
            llm = self.llm.share()
            if stream:
                return self._astream(query, llm, files, hist, **kw)
            return llm(query, stream_output=False, llm_chat_history=hist,
                       lazyllm_files=files, **kw)
        except Exception as e:
            lazyllm.LOG.exception(e)
            raise
        finally:
            llm = None


class _BgeM3Embedding:
    def __init__(self, url: str, *, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout

    def __call__(self, inputs: Any, **_: Any) -> Any:
        single = isinstance(inputs, str)
        payload = {'inputs': [inputs] if single else list(inputs)}
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        vectors = response.json()
        return vectors[0] if single else vectors


class _Qwen3Rerank:
    def __init__(self, url: str, model: str, *, timeout: float = 30.0):
        self.url = url
        self.model = model
        self.timeout = timeout

    def __call__(self, query: str, *, documents: List[str], top_n: int = None, **_: Any) -> List[tuple[int, float]]:
        payload = {
            'model': self.model,
            'query': query,
            'documents': documents,
        }
        if top_n is not None:
            payload['top_n'] = top_n
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        results = response.json().get('results', [])
        return [(int(item['index']), float(item['relevance_score'])) for item in results]


@functools.lru_cache(maxsize=64)
def _write_auto_model_config(serialized_config: str) -> str:
    config = yaml.safe_load(serialized_config)
    model_name = config['model']
    digest = hashlib.sha256(serialized_config.encode('utf-8')).hexdigest()[:16]
    safe_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', model_name).strip('-') or 'model'
    _RUNTIME_AUTO_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    config_path = _RUNTIME_AUTO_MODEL_DIR / f'{safe_name}-{digest}.yaml'
    temp_fd, temp_path = tempfile.mkstemp(
        dir=_RUNTIME_AUTO_MODEL_DIR, prefix=f'.{safe_name}-{digest}-', suffix='.yaml',
    )
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            yaml.safe_dump({model_name: [config]}, f, sort_keys=False)
        os.replace(temp_path, config_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise
    return str(config_path)


def _build_auto_model(model_name: str, config: Dict[str, Any]):
    cfg = deepcopy(config)
    source = cfg.get('source')
    model_type = cfg.get('type')
    if source == 'bgem3embed' and model_type == 'embed':
        return _BgeM3Embedding(cfg['url'])
    if source == 'qwen3rerank' and model_type == 'rerank':
        return _Qwen3Rerank(cfg['url'], model_name)
    cfg['model'] = model_name
    serialized = yaml.safe_dump(cfg, sort_keys=True)
    return AutoModel(model=model_name, config=_write_auto_model_config(serialized))


def get_automodel(role: str, *, wrap_simple_llm: bool = False) -> Any:
    with _lock:
        if role not in _base_models:
            model_name, config = get_role_config(role)
            _base_models[role] = _build_auto_model(model_name, config)
        base = _base_models[role]
        if not wrap_simple_llm:
            return base
        if role not in _wrapped_models:
            _wrapped_models[role] = _StreamingLlmModule(llm=base)
        return _wrapped_models[role]


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
