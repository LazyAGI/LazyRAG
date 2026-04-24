from __future__ import annotations

from functools import wraps
from socket import gaierror
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote

import lazyllm
from lazyllm import fc_register
from httpx import ConnectError, HTTPError, HTTPStatusError, NetworkError, TimeoutException
from lazyllm.thirdparty import httpx
from lazyllm.tools.tools.search import ArxivSearch, BingSearch, BochaSearch, GoogleSearch, WikipediaSearch


_MAX_TEXT_LEN = 2000
_DEFAULT_WEB_SOURCES = ['bocha', 'google', 'bing', 'wikipedia']
_WIKIPEDIA_API_PATH = '/w/api.php'
_DEFAULT_WIKIPEDIA_URLS = {
    'zh': 'https://zh.wikipedia.org',
    'en': 'https://en.wikipedia.org',
}
_DEFAULT_WIKIPEDIA_USER_AGENT = 'LazyRAG/1.0 (Wikipedia search integration)'


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


def _agentic_config() -> Dict[str, Any]:
    config = lazyllm.globals.get('agentic_config') or {}
    return config if isinstance(config, dict) else {}


def _config_str(config: Dict[str, Any], key: str, default: str = '') -> str:
    value = config.get(key)
    return str(value if value is not None else default).strip()


def _config_int(config: Dict[str, Any], key: str, default: int) -> int:
    value = config.get(key)
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_lang(lang: str) -> str:
    normalized = str(lang or 'zh').strip().lower()
    return normalized if normalized in ('zh', 'en') else 'zh'


def _normalize_auto_sources(value: Any) -> List[str]:
    if isinstance(value, str):
        items = [part.strip().lower() for part in value.split(',')]
    elif isinstance(value, list):
        items = [str(part).strip().lower() for part in value]
    else:
        items = list(_DEFAULT_WEB_SOURCES)
    return [item for item in items if item in {'google', 'bing', 'bocha', 'wikipedia'}] or list(_DEFAULT_WEB_SOURCES)


def _truncate_text(text: Any, max_len: int = _MAX_TEXT_LEN) -> str:
    if text is None:
        return ''
    raw = text if isinstance(text, str) else str(text)
    return raw if len(raw) <= max_len else f'{raw[:max_len]}...'


def _serialize_item(item: Dict[str, Any], content: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        'title': item.get('title', ''),
        'url': item.get('url', ''),
        'snippet': item.get('snippet', ''),
        'source': item.get('source', ''),
    }
    extra = item.get('extra')
    if isinstance(extra, dict) and extra:
        payload['extra'] = extra
    if content:
        payload['content'] = _truncate_text(content)
    return payload


def _error_details(exc: Exception) -> Dict[str, Any]:
    return {
        'error': str(exc),
        'error_type': type(exc).__name__,
    }


def _search_failure(query: str, source: str, details: Dict[str, Any], *, lang: Optional[str] = None,
                    tried_sources: Optional[List[str]] = None) -> Dict[str, Any]:
    payload = {
        'success': False,
        'status': 'search_error',
        'query': query,
        'resolved_source': source,
        'total': 0,
        'items': [],
        **details,
    }
    if lang is not None:
        payload['lang'] = lang
    if tried_sources is not None:
        payload['tried_sources'] = tried_sources
    return payload


def _classify_search_exception(exc: Exception) -> Dict[str, Any]:
    message = str(exc)
    if isinstance(exc, ConnectError):
        return {
            'status': 'network_unreachable',
            'reason': f'search provider is unreachable: {message}',
            **_error_details(exc),
        }
    if isinstance(exc, (TimeoutException, gaierror)):
        return {
            'status': 'request_timeout',
            'reason': f'search request timed out or name resolution failed: {message}',
            **_error_details(exc),
        }
    if isinstance(exc, HTTPStatusError):
        status_code = exc.response.status_code if exc.response is not None else None
        return {
            'status': 'http_error',
            'reason': f'search provider returned HTTP error{f" {status_code}" if status_code else ""}: {message}',
            'http_status': status_code,
            **_error_details(exc),
        }
    if isinstance(exc, (HTTPError, NetworkError)):
        return {
            'status': 'request_failed',
            'reason': f'search request failed: {message}',
            **_error_details(exc),
        }
    return {
        'status': 'search_error',
        'reason': f'search failed: {message}',
        **_error_details(exc),
    }


def _build_wikipedia_search(config: Dict[str, Any], lang: str) -> WikipediaSearch:
    base_url = _config_str(
        config,
        'web_search_wikipedia_base_url',
        _DEFAULT_WIKIPEDIA_URLS.get(_normalize_lang(lang), _DEFAULT_WIKIPEDIA_URLS['zh']),
    )
    timeout = _config_int(config, 'web_search_timeout', 10)
    return WikipediaSearch(base_url=base_url, timeout=timeout, source_name='wikipedia')


def _wikipedia_headers(config: Dict[str, Any]) -> Dict[str, str]:
    return {
        'User-Agent': _config_str(
            config,
            'web_search_wikipedia_user_agent',
            _DEFAULT_WIKIPEDIA_USER_AGENT,
        ),
    }


def _get_json(url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
              timeout: int = 10) -> Dict[str, Any]:
    response = httpx.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _post_json(url: str, *, json_body: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
               timeout: int = 10) -> Dict[str, Any]:
    response = httpx.post(url, json=json_body, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _provider_available(config: Dict[str, Any], source: str) -> bool:
    if source == 'wikipedia':
        return True
    if source == 'google':
        return bool(_config_str(config, 'web_search_google_api_key')) and bool(
            _config_str(config, 'web_search_google_search_engine_id')
        )
    if source == 'bing':
        return bool(_config_str(config, 'web_search_bing_subscription_key'))
    if source == 'bocha':
        return bool(_config_str(config, 'web_search_bocha_api_key'))
    return False


def _build_provider(config: Dict[str, Any], source: str, lang: str):
    timeout = _config_int(config, 'web_search_timeout', 10)
    if source == 'wikipedia':
        return _build_wikipedia_search(config, lang)
    if source == 'google':
        api_key = _config_str(config, 'web_search_google_api_key')
        search_engine_id = _config_str(config, 'web_search_google_search_engine_id')
        if not api_key or not search_engine_id:
            raise ValueError('google search is not configured')
        return GoogleSearch(
            custom_search_api_key=api_key,
            search_engine_id=search_engine_id,
            timeout=timeout,
            source_name='google',
        )
    if source == 'bing':
        subscription_key = _config_str(config, 'web_search_bing_subscription_key')
        if not subscription_key:
            raise ValueError('bing search is not configured')
        endpoint = _config_str(config, 'web_search_bing_endpoint')
        return BingSearch(
            subscription_key=subscription_key,
            endpoint=endpoint or None,
            timeout=timeout,
            source_name='bing',
        )
    if source == 'bocha':
        api_key = _config_str(config, 'web_search_bocha_api_key')
        if not api_key:
            raise ValueError('bocha search is not configured')
        base_url = _config_str(config, 'web_search_bocha_base_url', 'https://api.bochaai.com')
        return BochaSearch(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            source_name='bocha',
        )
    raise ValueError(f'unsupported web_search source: {source}')


def _search_wikipedia(config: Dict[str, Any], query: str, topk: int, lang: str) -> List[Dict[str, Any]]:
    base_url = _config_str(
        config,
        'web_search_wikipedia_base_url',
        _DEFAULT_WIKIPEDIA_URLS.get(_normalize_lang(lang), _DEFAULT_WIKIPEDIA_URLS['zh']),
    ).rstrip('/')
    timeout = _config_int(config, 'web_search_timeout', 10)
    data = _get_json(
        f'{base_url}{_WIKIPEDIA_API_PATH}',
        params={
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srlimit': min(topk, 50),
            'format': 'json',
        },
        headers=_wikipedia_headers(config),
        timeout=timeout,
    )
    items = data.get('query', {}).get('search') or []
    results = []
    for item in items:
        title = item.get('title', '')
        snippet = str(item.get('snippet') or '')
        snippet = snippet.replace('<span class=\"searchmatch\">', '').replace('</span>', '')
        results.append({
            'title': title,
            'url': f'{base_url}/wiki/{quote(title.replace(" ", "_"))}',
            'snippet': snippet,
            'source': 'wikipedia',
            'extra': {'pageid': item.get('pageid')},
        })
    return results


def _search_google(config: Dict[str, Any], query: str, topk: int) -> List[Dict[str, Any]]:
    api_key = _config_str(config, 'web_search_google_api_key')
    search_engine_id = _config_str(config, 'web_search_google_search_engine_id')
    data = _get_json(
        'https://customsearch.googleapis.com/customsearch/v1',
        params={
            'key': api_key,
            'cx': search_engine_id,
            'q': query,
            'start': 0,
            'num': min(topk, 10),
        },
        timeout=_config_int(config, 'web_search_timeout', 10),
    )
    items = data.get('items') or []
    return [
        {
            'title': item.get('title', ''),
            'url': item.get('link', ''),
            'snippet': item.get('snippet', ''),
            'source': 'google',
        }
        for item in items
    ]


def _search_bing(config: Dict[str, Any], query: str, topk: int) -> List[Dict[str, Any]]:
    subscription_key = _config_str(config, 'web_search_bing_subscription_key')
    endpoint = _config_str(config, 'web_search_bing_endpoint', 'https://api.bing.microsoft.com/v7.0/search')
    data = _get_json(
        endpoint,
        params={'q': query, 'count': min(topk, 50)},
        headers={'Ocp-Apim-Subscription-Key': subscription_key},
        timeout=_config_int(config, 'web_search_timeout', 10),
    )
    if data.get('_type') == 'ErrorResponse':
        raise RuntimeError(str(data))
    items = data.get('webPages', {}).get('value') or []
    return [
        {
            'title': item.get('name', ''),
            'url': item.get('url', ''),
            'snippet': item.get('snippet', ''),
            'source': 'bing',
        }
        for item in items
    ]


def _search_bocha(config: Dict[str, Any], query: str, topk: int) -> List[Dict[str, Any]]:
    api_key = _config_str(config, 'web_search_bocha_api_key')
    base_url = _config_str(config, 'web_search_bocha_base_url', 'https://api.bochaai.com').rstrip('/')
    data = _post_json(
        f'{base_url}/v1/web-search',
        json_body={'query': query, 'count': min(topk, 20), 'summary': False},
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        timeout=_config_int(config, 'web_search_timeout', 10),
    )
    items = data.get('results') or data.get('data') or data.get('items') or []
    if isinstance(items, dict):
        items = items.get('value', items.get('results', [])) or []
    return [
        {
            'title': item.get('title') or item.get('name') or '',
            'url': item.get('url') or item.get('link') or '',
            'snippet': item.get('snippet') or item.get('description') or item.get('summary') or '',
            'source': 'bocha',
        }
        for item in items
        if isinstance(item, dict)
    ]


def _run_search(config: Dict[str, Any], provider: Any, source: str, query: str, topk: int,
                lang: str) -> List[Dict[str, Any]]:
    if source == 'wikipedia':
        return _search_wikipedia(config, query, topk, lang)
    if source == 'google':
        return _search_google(config, query, topk)
    if source == 'bing':
        return _search_bing(config, query, topk)
    if source == 'bocha':
        return _search_bocha(config, query, topk)
    raise ValueError(f'unsupported web_search source: {source}')


def _run_search_with_error(
    config: Dict[str, Any],
    provider: Any,
    source: str,
    query: str,
    topk: int,
    lang: str,
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    try:
        return _run_search(config, provider, source, query, topk, lang), None
    except Exception as exc:
        return [], _classify_search_exception(exc)


def _resolve_source(
    config: Dict[str, Any],
    source: str,
    lang: str,
) -> tuple[str, Any, List[str]]:
    requested = str(source or 'auto').strip().lower()
    if requested != 'auto':
        provider = _build_provider(config, requested, lang)
        return requested, provider, [requested]

    tried: List[str] = []
    for candidate in _normalize_auto_sources(config.get('web_search_auto_sources')):
        tried.append(candidate)
        if not _provider_available(config, candidate):
            continue
        return candidate, _build_provider(config, candidate, lang), tried

    provider = _build_wikipedia_search(config, lang)
    if 'wikipedia' not in tried:
        tried.append('wikipedia')
    return 'wikipedia', provider, tried


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def web_search(
    query: str,
    source: Literal['auto', 'wikipedia', 'google', 'bing', 'bocha'] = 'auto',
    topk: int = 5,
    lang: Literal['zh', 'en'] = 'zh',
    include_content: bool = False,
) -> Dict[str, Any]:
    """Search public web information as a supplement when knowledge-base
    retrieval is insufficient.

    Prefer `kb_search` first. Use this tool only when the knowledge base
    has no relevant results, the returned evidence is clearly insufficient,
    or the user is asking for public information outside the knowledge base.

    This tool supports multiple providers through a single interface:
    `source='auto'|'wikipedia'|'google'|'bing'|'bocha'`.
    In `auto` mode, the provider order is read from runtime config and falls
    back to Wikipedia when no keyed provider is configured.

    Args:
        query: Natural-language search query.
        source: Search provider selector. Use `auto` unless the user
            explicitly needs a specific provider.
        topk: Maximum number of result items to return.
        lang: Preferred language for Wikipedia fallback. Currently supports
            `zh` and `en`.
        include_content: Whether to fetch and include page content for each
            result item. Keep this `False` unless extra detail is necessary.

    Returns:
        A compact dict containing the resolved provider, query, and items.
    """
    normalized_query = str(query or '').strip()
    if not normalized_query:
        raise ValueError('query is required')

    config = _agentic_config()
    resolved_lang = _normalize_lang(lang)
    limit = max(1, min(int(topk), 10))
    resolved_source, provider, tried_sources = _resolve_source(config, source, resolved_lang)
    items, error = _run_search_with_error(config, provider, resolved_source, normalized_query, limit, resolved_lang)
    if error is not None:
        return _search_failure(
            normalized_query,
            resolved_source,
            error,
            lang=resolved_lang,
            tried_sources=tried_sources,
        )
    items = items[:limit]

    serialized_items = []
    for item in items:
        content = provider.get_content(item) if include_content else None
        serialized_items.append(_serialize_item(item, content=content))

    return {
        'success': True,
        'status': 'ok' if serialized_items else 'no_results',
        'query': normalized_query,
        'requested_source': source,
        'resolved_source': resolved_source,
        'tried_sources': tried_sources,
        'lang': resolved_lang,
        'total': len(serialized_items),
        'items': serialized_items,
    }


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def arxiv_search(
    query: str,
    max_results: int = 5,
    include_content: bool = False,
    sort_by: Literal['relevance', 'lastUpdatedDate', 'submittedDate'] = 'relevance',
) -> Dict[str, Any]:
    """Search arXiv papers for academic questions such as paper titles,
    authors, abstracts, or arXiv identifiers.

    Prefer this tool over `web_search` when the user is asking about papers,
    research topics, or arXiv records.

    Args:
        query: Paper title, topic, author keywords, or arXiv id related text.
        max_results: Maximum number of result items to return.
        include_content: Whether to include the paper abstract text in the
            returned items.
        sort_by: arXiv sort field.

    Returns:
        A compact dict with arXiv search results.
    """
    normalized_query = str(query or '').strip()
    if not normalized_query:
        raise ValueError('query is required')

    config = _agentic_config()
    timeout = _config_int(config, 'arxiv_search_timeout', 15)
    limit = max(1, min(int(max_results), 10))
    provider = ArxivSearch(timeout=timeout, source_name='arxiv')
    try:
        items = provider.search(normalized_query, max_results=limit, sort_by=sort_by)[:limit]
    except Exception as exc:
        return _search_failure(normalized_query, 'arxiv', _classify_search_exception(exc))

    serialized_items = []
    for item in items:
        content = provider.get_content(item) if include_content else None
        serialized_items.append(_serialize_item(item, content=content))

    return {
        'success': True,
        'status': 'ok' if serialized_items else 'no_results',
        'query': normalized_query,
        'source': 'arxiv',
        'sort_by': sort_by,
        'total': len(serialized_items),
        'items': serialized_items,
    }
