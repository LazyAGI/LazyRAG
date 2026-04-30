from __future__ import annotations

from functools import wraps
from socket import gaierror
from typing import Any, Dict, List, Literal, Optional, Tuple

import lazyllm
import requests
from bs4 import BeautifulSoup
from httpx import ConnectError, HTTPError, HTTPStatusError, NetworkError, TimeoutException
from lazyllm import fc_register
from lazyllm.tools.tools.search import ArxivSearch, BingSearch, BochaSearch, GoogleSearch, WikipediaSearch


_MAX_TEXT_LEN = 2000
_MAX_FETCH_TEXT_LEN = 4000
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


def _absolute_url(url: str) -> str:
    normalized = str(url or '').strip()
    if not normalized:
        return ''
    if normalized.startswith(('http://', 'https://')):
        return normalized
    return f'https://{normalized}'


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
        return provider(query, limit=topk, raise_on_error=True)[:topk]
    if source == 'google':
        return provider(query, date_restrict='', raise_on_error=True)[:topk]
    if source == 'bing':
        return provider(query, count=topk, raise_on_error=True)[:topk]
    if source == 'bocha':
        return provider(query, count=topk, summary=False, raise_on_error=True)[:topk]
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


def _fetch_timeout(config: Dict[str, Any]) -> int:
    return _config_int(config, 'url_fetch_timeout', _config_int(config, 'web_search_timeout', 10))


def _fetch_text_limit(config: Dict[str, Any]) -> int:
    return max(200, _config_int(config, 'url_fetch_max_length', _MAX_FETCH_TEXT_LEN))


def _extract_page_text(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')

    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()

    content_root = soup.find('main') or soup.find('article') or soup.body or soup
    lines: List[str] = []
    for node in content_root.find_all(['h1', 'h2', 'h3', 'p', 'li']):
        text = node.get_text(' ', strip=True)
        if text:
            lines.append(text)

    if not lines:
        text = content_root.get_text('\n', strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

    deduped_lines: List[str] = []
    seen: set[str] = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        deduped_lines.append(line)
    return '\n'.join(deduped_lines)


def _extract_page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    og_title = soup.find('meta', attrs={'property': 'og:title'})
    if og_title and og_title.get('content'):
        return str(og_title['content']).strip()
    return ''


def _extract_page_description(soup: BeautifulSoup) -> str:
    candidates = [
        {'name': 'description'},
        {'property': 'og:description'},
    ]
    for attrs in candidates:
        tag = soup.find('meta', attrs=attrs)
        if tag and tag.get('content'):
            return str(tag['content']).strip()
    return ''


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def web_search(
    query: str,
    source: Literal['auto', 'wikipedia', 'google', 'bing', 'bocha'] = 'auto',
    topk: int = 5,
    lang: Literal['zh', 'en'] = 'zh',
    include_content: bool = False,
) -> Dict[str, Any]:
    """当知识库检索不足时，补充检索公开网页信息。

    应优先使用 `kb_search`。只有在知识库没有相关结果、返回证据明显不足，
    或用户询问的是知识库外的公开信息时，才使用该工具。

    该工具通过统一接口支持多个搜索源：`source='auto'|'wikipedia'|'google'|'bing'|'bocha'`。
    在 `auto` 模式下，会按配置顺序依次尝试搜索源；未配置的搜索源会被跳过，
    运行失败时会自动尝试下一个候选源，Wikipedia 始终作为最终兜底源追加。

    参数：
        query: 自然语言搜索查询。
        source: 搜索源选择器。除非用户明确要求特定搜索源，否则使用 `auto`。
        topk: 最多返回的结果条数。
        lang: Wikipedia 兜底检索的首选语言。目前支持 `zh` 和 `en`。
        include_content: 是否抓取并包含每条结果的页面内容。除非确实需要更多细节，否则保持为 `False`。

    返回：
        包含实际搜索源、查询和结果条目的紧凑字典。
    """
    normalized_query = str(query or '').strip()
    if not normalized_query:
        raise ValueError('query 是必填参数')

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
    """针对论文标题、作者、摘要或 arXiv 编号等学术问题检索 arXiv 论文。

    当用户询问论文、研究主题或 arXiv 记录时，应优先使用该工具，而不是 `web_search`。

    参数：
        query: 论文标题、研究主题、作者关键词或 arXiv ID 相关文本。
        max_results: 最多返回的结果条数。
        include_content: 是否在返回结果中包含论文摘要文本。
        sort_by: arXiv 排序字段。

    返回：
        包含 arXiv 检索结果的紧凑字典。
    """
    normalized_query = str(query or '').strip()
    if not normalized_query:
        raise ValueError('query 是必填参数')

    config = _agentic_config()
    timeout = _config_int(config, 'arxiv_search_timeout', 15)
    limit = max(1, min(int(max_results), 10))
    provider = ArxivSearch(timeout=timeout, source_name='arxiv')
    try:
        items = provider(
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


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def url_fetch(
    url: str,
) -> Dict[str, Any]:
    """抓取并整理公开网页中可读的正文内容。

    当用户提供具体 URL，或搜索结果已经定位到需要直接查看的页面时，使用该工具。

    参数：
        url: 绝对 URL，或可规范化为 HTTPS 的域名/路径。

    返回：
        包含页面元数据和抽取正文内容的紧凑字典。
    """
    normalized_url = _absolute_url(url)
    if not normalized_url:
        raise ValueError('url 是必填参数')

    config = _agentic_config()
    timeout = _fetch_timeout(config)
    text_limit = _fetch_text_limit(config)
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
    }

    with requests.sessions.Session() as session:
        response = session.get(
            normalized_url,
            timeout=timeout,
            headers=headers,
            allow_redirects=True,
        )
        response.raise_for_status()

    content_type = str(response.headers.get('Content-Type') or '').lower()
    if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
        raw_text = response.text.strip()
        return {
            'success': True,
            'status': 'ok',
            'url': normalized_url,
            'final_url': response.url,
            'status_code': response.status_code,
            'content_type': content_type,
            'title': '',
            'description': '',
            'content': _truncate_text(raw_text, text_limit),
        }

    soup = BeautifulSoup(response.text, 'html.parser')
    return {
        'success': True,
        'status': 'ok',
        'url': normalized_url,
        'final_url': response.url,
        'status_code': response.status_code,
        'content_type': content_type,
        'title': _extract_page_title(soup),
        'description': _truncate_text(_extract_page_description(soup), 500),
        'content': _truncate_text(_extract_page_text(response.text), text_limit),
    }
