from __future__ import annotations

from functools import wraps
from socket import gaierror
from typing import Any, Dict, List, Literal, Optional, Tuple

import lazyllm
from httpx import ConnectError, HTTPError, HTTPStatusError, NetworkError, TimeoutException
from lazyllm import fc_register
from lazyllm.tools.tools.search import ArxivSearch, BingSearch, BochaSearch, GoogleSearch, WikipediaSearch


_MAX_TEXT_LEN = 2000
_DEFAULT_WEB_SOURCES = ['bocha', 'google', 'bing', 'wikipedia']
_SUPPORTED_WEB_SOURCES = {'google', 'bing', 'bocha', 'wikipedia'}
_DEFAULT_WIKIPEDIA_URLS = {
    'zh': 'https://zh.wikipedia.org',
    'en': 'https://en.wikipedia.org',
}


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
    normalized = [item for item in items if item in _SUPPORTED_WEB_SOURCES]
    return normalized or list(_DEFAULT_WEB_SOURCES)


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


def _search_provider(provider: Any, source: str, query: str, topk: int) -> List[Dict[str, Any]]:
    if source == 'wikipedia':
        return provider.search(query, limit=topk, raise_on_error=True)[:topk]
    if source == 'google':
        return provider.search(query, date_restrict='', raise_on_error=True)[:topk]
    if source == 'bing':
        return provider.search(query, count=topk, raise_on_error=True)[:topk]
    if source == 'bocha':
        return provider.search(query, count=topk, summary=False, raise_on_error=True)[:topk]
    raise ValueError(f'unsupported web_search source: {source}')


def _candidate_sources(config: Dict[str, Any], requested_source: str) -> List[str]:
    if requested_source != 'auto':
        return [requested_source]

    candidates = _normalize_auto_sources(config.get('web_search_auto_sources'))
    if 'wikipedia' not in candidates:
        candidates.append('wikipedia')
    return candidates


def _run_candidate_searches(
    config: Dict[str, Any],
    source: str,
    query: str,
    topk: int,
    lang: str,
) -> Tuple[Optional[str], List[str], List[Dict[str, Any]], Optional[Any], Optional[Dict[str, Any]]]:
    requested = str(source or 'auto').strip().lower()
    tried_sources: List[str] = []
    last_error: Optional[Dict[str, Any]] = None
    last_error_source: Optional[str] = None
    last_non_error_source: Optional[str] = None

    for candidate in _candidate_sources(config, requested):
        tried_sources.append(candidate)
        if requested == 'auto' and not _provider_available(config, candidate):
            continue

        provider = _build_provider(config, candidate, lang)
        try:
            items = _search_provider(provider, candidate, query, topk)
        except Exception as exc:
            last_error = _classify_search_exception(exc)
            last_error_source = candidate
            if requested != 'auto':
                return candidate, tried_sources, [], None, last_error
            continue

        last_non_error_source = candidate
        if items:
            return candidate, tried_sources, items[:topk], provider, None
        if requested != 'auto':
            return candidate, tried_sources, [], provider, None

    resolved_source = last_non_error_source or last_error_source
    return resolved_source, tried_sources, [], None, last_error


def _content_for_item(provider: Any, item: Dict[str, Any], include_content: bool) -> Optional[str]:
    if not include_content:
        return None
    return provider.get_content(item)


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
    In `auto` mode, providers are tried in configured order. Unconfigured
    providers are skipped, runtime failures fall through to the next
    candidate, and Wikipedia is always appended as the final fallback.

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
    resolved_source, tried_sources, items, provider, error = _run_candidate_searches(
        config,
        source,
        normalized_query,
        limit,
        resolved_lang,
    )
    if error is not None:
        return _search_failure(
            normalized_query,
            resolved_source or str(source),
            error,
            lang=resolved_lang,
            tried_sources=tried_sources,
        )

    serialized_items = []
    for item in items:
        content = _content_for_item(provider, item, include_content) if provider is not None else None
        serialized_items.append(_serialize_item(item, content=content))

    return {
        'success': True,
        'status': 'ok' if serialized_items else 'no_results',
        'query': normalized_query,
        'requested_source': source,
        'resolved_source': resolved_source or str(source),
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
        items = provider.search(
            normalized_query,
            max_results=limit,
            sort_by=sort_by,
            raise_on_error=True,
        )[:limit]
    except Exception as exc:
        return _search_failure(normalized_query, 'arxiv', _classify_search_exception(exc))

    serialized_items = []
    for item in items:
        content = _content_for_item(provider, item, include_content)
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
