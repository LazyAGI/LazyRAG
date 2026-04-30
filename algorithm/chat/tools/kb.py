import json
import os
from functools import wraps
from typing import Any, Dict, List, Optional

import lazyllm
import requests

from lazyllm import fc_register

from chat.pipelines.builders.get_ppl_search import get_ppl_search

_MAX_TEXT_LEN = 1200
_MAX_RESULT_ITEMS = 50
_DEFAULT_KB_URL = os.getenv('LAZYRAG_AGENTIC_KB_URL', 'http://lazyllm-algo:8000')
_DEFAULT_ES_URL = os.getenv('LAZYRAG_OPENSEARCH_URI', 'https://opensearch:9200')
_DEFAULT_ES_USER = os.getenv('LAZYRAG_OPENSEARCH_USER', 'admin')
_DEFAULT_ES_PASSWORD = os.getenv('LAZYRAG_OPENSEARCH_PASSWORD', '')
_CITATION_REFS_KEY = '_citation_sources'
_CITATION_KEY_MAP_KEY = '_citation_key_map'
_CITATION_NEXT_KEY = '_citation_next_index'


def _tool_failure(tool_name: str, exc: Exception) -> Dict[str, Any]:
    return {
        'success': False,
        'reason': f'{tool_name} failed: {exc}',
        'error': str(exc),
        'error_type': type(exc).__name__,
    }


def _handle_tool_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return _tool_failure(func.__name__, exc)

    return wrapper


def _safe_getattr(obj: Any, key: str, default: Any = None) -> Any:
    try:
        return getattr(obj, key)
    except Exception:
        return default


def _truncate_text(text: Any, max_len: int = _MAX_TEXT_LEN) -> str:
    if text is None:
        return ''
    raw = text if isinstance(text, str) else str(text)
    return raw if len(raw) <= max_len else f'{raw[:max_len]}...'


def _parse_number_range(number: Any) -> tuple[int, int]:
    if isinstance(number, str):
        raw = number.strip()
        try:
            number = json.loads(raw)
        except (TypeError, ValueError):
            if ',' in raw:
                number = [part.strip() for part in raw.split(',', 1)]
            elif '-' in raw:
                number = [part.strip() for part in raw.split('-', 1)]
            else:
                number = raw

    if isinstance(number, (list, tuple)):
        if len(number) != 2:
            raise ValueError('number 范围必须是 [start, end]')
        start, end = int(number[0]), int(number[1])
    else:
        start = end = int(number)
    if start > end:
        start, end = end, start
    return start, end


def _serialize_doc_node_like(node: Any) -> Dict[str, Any]:
    metadata = _safe_getattr(node, 'metadata', {}) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    global_md = _safe_getattr(node, 'global_metadata', {}) or {}
    if not isinstance(global_md, dict):
        global_md = {}
    compact_metadata = {
        k: metadata[k]
        for k in (
            'type',
            'node_type',
            'index',
            'file_name',
            'source',
            'store_num',
            'lazyllm_store_num',
            'page',
            'bbox',
            'images',
        )
        if k in metadata
    }
    return {
        'uid': _safe_getattr(node, 'uid', None) or _safe_getattr(node, '_uid', None),
        'number': _safe_getattr(node, 'number', metadata.get('index')),
        'group': _safe_getattr(node, 'group', None) or _safe_getattr(node, '_group', None),
        'parent': _safe_getattr(node, '_parent', None),
        'score': _safe_getattr(node, 'relevance_score', None),
        'text': _truncate_text(_safe_getattr(node, 'text', '')),
        'docid': global_md.get('docid'),
        'kb_id': global_md.get('kb_id'),
        'file_name': compact_metadata.get('file_name') or global_md.get('file_name'),
        'metadata': compact_metadata,
        'global_metadata': global_md,
    }


def _agentic_config() -> Dict[str, Any]:
    config = lazyllm.globals.get('agentic_config') or {}
    return config if isinstance(config, dict) else {}


def _parse_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _normalize_es_url(url: Optional[str]) -> str:
    return (url or _DEFAULT_ES_URL).rstrip('/')


def _resolve_kb_name(config: Dict[str, Any]) -> str:
    resolved = config.get('kb_name')
    if not resolved:
        raise ValueError('agentic_config 中没有 kb_name 时，必须显式提供 kb_name')
    return resolved


def _resolve_kb_id(config: Dict[str, Any]) -> Optional[str]:
    kb_id = config.get('kb_id')
    if isinstance(kb_id, str):
        normalized = kb_id.strip()
        return normalized or None
    if isinstance(kb_id, list):
        for item in kb_id:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized:
                return normalized
    return None


def _resolve_index(config: Dict[str, Any], group: str) -> str:
    group = (group or 'block').strip()
    if group not in ('block', 'line'):
        raise ValueError("group 必须是 'block' 或 'line'")
    return f'col_{_resolve_kb_name(config)}_{group}'


def _term_filter(field: str, value: Any) -> Dict[str, Any]:
    return {
        'bool': {
            'should': [
                {'term': {field: value}},
                {'term': {f'{field}.keyword': value}},
            ],
            'minimum_should_match': 1,
        }
    }


def _opensearch_search(index: str, body: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    with requests.sessions.Session() as session:
        session.trust_env = False
        resp = session.post(
            f'{_normalize_es_url(config.get("es_url"))}/{index}/_search',
            auth=(config.get('es_user') or _DEFAULT_ES_USER, config.get('es_password') or _DEFAULT_ES_PASSWORD),
            json=body,
            verify=False,
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


def _source_to_result(hit: Dict[str, Any]) -> Dict[str, Any]:
    src = hit.get('_source') or {}
    meta = _parse_json_dict(src.get('meta'))
    global_meta = _parse_json_dict(src.get('global_meta'))
    return {
        'uid': src.get('uid') or hit.get('_id'),
        'number': src.get('number'),
        'group': src.get('group'),
        'parent': src.get('parent'),
        'docid': src.get('doc_id') or global_meta.get('docid'),
        'kb_id': src.get('kb_id') or global_meta.get('kb_id'),
        'score': hit.get('_score'),
        'text': _truncate_text(src.get('content')),
        'metadata': meta,
        'global_metadata': global_meta,
        'highlight': hit.get('highlight', {}).get('content', []),
    }


def _citation_key(item: Dict[str, Any]) -> Optional[str]:
    uid = item.get('uid') or item.get('segement_id')
    if uid:
        return f'uid:{uid}'
    docid = item.get('docid') or item.get('document_id')
    group = item.get('group') or item.get('group_name')
    number = item.get('number') or item.get('segment_number')
    if docid and group and number is not None:
        return f'node:{docid}:{group}:{number}'
    text = item.get('text') or item.get('content')
    if docid and text:
        return f'text:{docid}:{str(text)[:80]}'
    return None


def _file_name_from_item(item: Dict[str, Any]) -> str:
    metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
    global_md = item.get('global_metadata') if isinstance(item.get('global_metadata'), dict) else {}
    return (
        item.get('file_name')
        or global_md.get('file_name')
        or metadata.get('file_name')
        or metadata.get('source')
        or 'title_example'
    )


def _source_node_from_item(index: int, item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
    global_md = item.get('global_metadata') if isinstance(item.get('global_metadata'), dict) else {}
    content = item.get('text') if item.get('text') is not None else item.get('content', '')
    return {
        'file_id': '',
        'file_name': _file_name_from_item(item),
        'document_id': item.get('docid') or item.get('document_id') or global_md.get('docid', ''),
        'segement_id': item.get('uid') or item.get('segement_id') or '',
        'dataset_id': item.get('kb_id') or item.get('dataset_id') or global_md.get('kb_id', ''),
        'index': index,
        'content': content or '',
        'group_name': item.get('group') or item.get('group_name') or '',
        'segment_number': (
            metadata.get('store_num')
            or metadata.get('lazyllm_store_num')
            or item.get('number')
            or item.get('segment_number')
            or -1
        ),
        'page': metadata.get('page', -1),
        'bbox': metadata.get('bbox', []),
    }


def _register_citation_item(item: Dict[str, Any]) -> Dict[str, Any]:
    text = item.get('text') if item.get('text') is not None else item.get('content')
    if not text:
        return item

    config = _agentic_config()
    refs = config.setdefault(_CITATION_REFS_KEY, {})
    key_map = config.setdefault(_CITATION_KEY_MAP_KEY, {})
    key = _citation_key(item)
    if not key:
        return item

    index = key_map.get(key)
    if index is None:
        index = int(config.get(_CITATION_NEXT_KEY) or 1)
        config[_CITATION_NEXT_KEY] = index + 1
        key_map[key] = index
        refs[index] = _source_node_from_item(index, item)

    item['citation_index'] = index
    item['ref'] = f'[[{index}]]'
    return item


def _annotate_citations(result: Any) -> Any:
    if isinstance(result, dict):
        if any(k in result for k in ('text', 'content', 'uid', 'docid', 'document_id')):
            _register_citation_item(result)
        if isinstance(result.get('items'), list):
            result['items'] = [
                _annotate_citations(item) if isinstance(item, dict) else item
                for item in result['items']
            ]
        if isinstance(result.get('current_node'), dict):
            result['current_node'] = _annotate_citations(result['current_node'])
        return result
    if isinstance(result, list):
        return [
            _annotate_citations(item) if isinstance(item, dict) else item
            for item in result
        ]
    return result


def _node_id_query(node_id: str) -> Dict[str, Any]:
    return {
        'bool': {
            'should': [
                {'ids': {'values': [node_id]}},
                {'term': {'uid': node_id}},
                {'term': {'uid.keyword': node_id}},
            ],
            'minimum_should_match': 1,
        }
    }


def _find_node_by_id(node_id: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kb_id = _resolve_kb_id(config)
    filters = []
    if kb_id:
        filters.append(_term_filter('kb_id', kb_id))
    body = {
        'size': 1,
        '_source': ['uid', 'doc_id', 'kb_id', 'group', 'content', 'meta', 'global_meta', 'type', 'number', 'parent'],
        'query': {
            'bool': {
                'filter': filters,
                'must': [_node_id_query(node_id)],
            }
        },
    }
    for group in ('block', 'line'):
        index_name = _resolve_index(config, group)
        hits = _opensearch_search(index_name, body, config).get('hits', {}).get('hits', [])
        if hits:
            return hits[0]
    return None


def _serialize_kb_result(result: Any) -> Any:
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    if isinstance(result, dict):
        result = dict(result)
        if isinstance(result.get('items'), list):
            serialized = _serialize_kb_result(result['items'])
            if isinstance(serialized, dict):
                result['items'] = serialized.get('items', result['items'])
                result.setdefault('total', serialized.get('total'))
        return result
    if isinstance(result, tuple):
        result = list(result)
    if isinstance(result, list):
        serialized_items = []
        for item in result[:_MAX_RESULT_ITEMS]:
            if isinstance(item, (str, int, float, bool)) or item is None:
                serialized_items.append(item)
                continue
            if isinstance(item, dict):
                serialized_items.append(item)
                continue
            if _safe_getattr(item, 'uid', None) is not None or _safe_getattr(item, 'text', None) is not None:
                serialized_items.append(_serialize_doc_node_like(item))
                continue
            serialized_items.append(_truncate_text(item, max_len=400))
        return {
            'total': len(result),
            'items': serialized_items,
        }
    return _truncate_text(result, max_len=400)


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def kb_search(
    query: str,
    retriever_configs: Optional[List[Dict[str, Any]]] = None,
    topk: Optional[int] = None,
    k_max: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None,
    files: Optional[List[str]] = None,
) -> Any:
    """检索知识库或用户临时上传的文档，并返回检索结果。

    工具会根据 `files` 是否非空自动选择两条检索分支：

    分支 A：临时文件检索（提供 `files` 时）：
        在指定的上传文件 ID 上运行 TempDocRetriever。若用户问题针对当前会话上传的文件，
        而不是持久化知识库，应使用该分支。

    分支 B：知识库检索（`files` 为空或未提供时）：
        执行多路知识库检索（稠密 + 稀疏、多粒度），随后进行 RRF 融合、重排、
        自适应 top-k 选择和上下文扩展。若用户问题针对知识库内容，应使用该分支。

    两条分支共享同一套重排、自适应 top-k 和上下文扩展阶段，因此 `topk` 与 `k_max`
    对两条分支都生效。

    参数：
        query: 用于检索的自然语言查询文本。
        retriever_configs: 多路检索器配置列表。仅对分支 B（知识库检索）有效。
            若为 None，则回退到运行时配置中的 `retrieval.retriever_configs`。
            每个元素是一个字典，包含以下字段：
            - group_name (str, 必填)：检索粒度，只能是 'line'（句子级）或 'block'（段落级）。
            - embed_keys (List[str], 必填)：该路检索使用的 embedding 模型键，必须与运行时
              配置中 `embeddings` 下声明的键一致，例如 ['embed_1'] 表示稠密检索，
              ['embed_2'] 表示稀疏检索。
            - topk (int, 可选)：融合前该路召回的候选节点数，默认 20。
            - target (str, 可选)：检索后的跨粒度目标分组，例如 group_name 为 'line' 时
              可设为 'block'，用于把命中的行提升到父 block。
            也可以在每个字典中加入 `lazyllm.Retriever` 支持的其他关键字参数。
        topk: 最终重排 top-k，用于限制重排后返回的节点数量，默认 20。
        k_max: 自适应 top-k 阶段的硬上限，该阶段会根据 token 预算动态裁剪结果，默认 10。
        filters: 应用于知识库检索器的元数据过滤条件（仅分支 B 有效）。例如
            {'file_name': 'report.pdf'} 会把检索限制在单个文件内。当提供 `files` 时忽略该参数。
        files: 临时文件 ID 列表（由用户在当前会话上传）。非空时切换到分支 A
            （TempDocRetriever）。默认读取 `agentic_config['temp_files']` 中的当前会话上传文件；
            可显式传入列表覆盖默认值，或传入 [] 强制使用分支 B。

    返回：
        `get_ppl_search(...)(payload)` 返回的检索结果。
    """
    agentic_config = lazyllm.globals.get('agentic_config') or {}
    kb_url = agentic_config.get('kb_url')
    kb_name = agentic_config.get('kb_name')

    if files is None:
        files = agentic_config.get('temp_files') or []

    payload = {
        'query': query,
        'filters': filters or {},
        'files': files,
    }
    resolved_kb_id = _resolve_kb_id(agentic_config)
    if resolved_kb_id:
        payload['filters']['kb_id'] = resolved_kb_id
    search_ppl = get_ppl_search(
        url=f'{kb_url},{kb_name}',
        retriever_configs=retriever_configs,
        topk=topk or 20,
        k_max=k_max or 10,
    )
    return _annotate_citations(_serialize_kb_result(search_ppl(payload)))


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def kb_get_parent_node(node_id: str) -> Dict[str, Any]:
    """根据节点 ID 获取目标节点的父节点。

    参数：
        node_id: 目标节点 ID。可以匹配 OpenSearch 文档 ID，也可以匹配节点的 ``uid`` 字段。

    返回：
        如果当前节点存在父节点且能够找到，则返回匹配到的父节点。
    """
    if not node_id:
        raise ValueError('node_id 是必填参数')

    config = _agentic_config()
    current_hit = _find_node_by_id(node_id, config)
    if not current_hit:
        return {
            'node_id': node_id,
            'current_node': None,
            'parent_id': None,
            'total': 0,
            'items': [],
        }

    current = _source_to_result(current_hit)
    parent_id = current.get('parent')
    if not parent_id:
        return _annotate_citations({
            'node_id': node_id,
            'current_node': current,
            'parent_id': None,
            'total': 0,
            'items': [],
        })

    parent_hit = _find_node_by_id(parent_id, config)
    parent = _source_to_result(parent_hit) if parent_hit else None
    return _annotate_citations({
        'node_id': node_id,
        'current_node': current,
        'parent_id': parent_id,
        'total': 1 if parent else 0,
        'items': [parent] if parent else [],
    })


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def kb_get_window_nodes(
    docid: str,
    number: Any,
    group: str = 'block',
) -> Dict[str, Any]:
    """使用 LazyLLM Document 按编号读取目标文档中的节点。

    参数：
        docid: 目标文档 ID。
        number: 节点编号或闭区间编号范围。传入 int 表示读取单个节点；传入
            ``[start, end]`` 或 ``"start,end"`` 表示读取该范围内所有节点。
        group: 节点分组，只能是 ``block`` 或 ``line``。

    返回：
        仅包含节点编号和内容的紧凑字典。
    """
    if not docid:
        raise ValueError('docid 是必填参数')
    if number is None:
        raise ValueError('number 是必填参数')

    start, end = _parse_number_range(number)

    numbers = set(range(start, end + 1))
    if len(numbers) > _MAX_RESULT_ITEMS:
        raise ValueError(f'number 范围不能超过 {_MAX_RESULT_ITEMS} 个节点')

    config = _agentic_config()
    kb_id = _resolve_kb_id(config)

    doc = lazyllm.tools.rag.Document(
        url=config.get('kb_url') or _DEFAULT_KB_URL,
        name=_resolve_kb_name(config),
    )

    nodes = doc.get_nodes(
        doc_ids=[docid],
        group=group,
        kb_id=kb_id,
        offset=max(start - 1, 0),
        limit=len(numbers),
        sort_by_number=True,
    )
    nodes = nodes if isinstance(nodes, list) else []
    nodes = [n for n in nodes if _safe_getattr(n, 'number', None) in numbers]
    nodes.sort(key=lambda n: (_safe_getattr(n, 'number', 0) or 0, _safe_getattr(n, 'uid', '') or ''))
    return _annotate_citations({
        'total': len(nodes),
        'items': [_serialize_doc_node_like(n) for n in nodes],
    })


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def kb_keyword_search(
    keyword: str,
    docid: str,
    group: str = 'block',
    phrase: bool = True,
    size: int = 10,
    sort_by: str = 'score',
) -> Dict[str, Any]:
    """在 OpenSearch 中检索某个目标文档内的关键词。

    参数：
        keyword: 要在 ``content`` 字段中检索的关键词或短语。
        docid: 目标文档 ID。
        group: 检索粒度，只能是 ``block`` 或 ``line``。
        phrase: 为 true 时使用 ``match_phrase``，否则使用 ``match``。
        size: 最大命中数量。
        sort_by: ``score`` 表示按相关性优先排序，``number`` 表示按文档顺序排序。

    返回：
        返回匹配节点、内容片段以及 OpenSearch 高亮结果。
    """
    if not keyword:
        raise ValueError('keyword 是必填参数')
    if not docid:
        raise ValueError('docid 是必填参数')

    config = _agentic_config()
    kb_id = _resolve_kb_id(config)
    size = max(1, min(int(size), _MAX_RESULT_ITEMS))
    text_query = {'match_phrase' if phrase else 'match': {'content': keyword}}
    sort = [{'number': {'order': 'asc'}}] if sort_by == 'number' else [
        {'_score': {'order': 'desc'}},
        {'number': {'order': 'asc'}},
    ]
    filters = [_term_filter('doc_id', docid)]
    if kb_id:
        filters.insert(0, _term_filter('kb_id', kb_id))
    body = {
        'size': size,
        '_source': ['uid', 'doc_id', 'kb_id', 'group', 'content', 'meta', 'global_meta', 'type', 'number', 'parent'],
        'query': {
            'bool': {
                'filter': filters,
                'must': [text_query],
            }
        },
        'sort': sort,
        'highlight': {
            'fields': {
                'content': {
                    'fragment_size': 180,
                    'number_of_fragments': 3,
                }
            }
        },
    }
    index_name = _resolve_index(config, group)
    hits = _opensearch_search(index_name, body, config).get('hits', {}).get('hits', [])
    return _annotate_citations({
        'index': index_name,
        'group': group,
        'docid': docid,
        'keyword': keyword,
        'total': len(hits),
        'items': [_source_to_result(hit) for hit in hits],
    })
