
from typing import Any, Dict, List, Optional, Union
import re
import requests

from lazyllm import LOG
from lazyllm.tools.rag.doc_node import DocNode, MetadataMode
from lazyllm import AutoModel
from lazyllm.module.llms.onlinemodule.base import LazyLLMOnlineEmbedModuleBase, LazyLLMOnlineRerankModuleBase


class BgeM3Embed(LazyLLMOnlineEmbedModuleBase):
    NO_PROXY = True

    def __init__(self, embed_url: str = '', embed_model_name: str = 'custom', api_key: str = None,
                 skip_auth: bool = True, batch_size: int = 16, **kw):
        super().__init__(model_series='bge', embed_url=embed_url, api_key='' if skip_auth else (api_key or ''),
                         embed_model_name=embed_model_name,
                         skip_auth=skip_auth, batch_size=batch_size, **kw)

    def _set_embed_url(self):
        pass

    def _encapsulated_data(self, input: Union[List, str], **kwargs):
        model = kwargs.get('model', self._embed_model_name)
        extras = {k: v for k, v in kwargs.items() if k not in ('model',)}
        if isinstance(input, str):
            json_data: Dict = {'inputs': input}
            if model:
                json_data['model'] = model
            json_data.update(extras)
            return json_data
        text_batch = [input[i: i + self._batch_size] for i in range(0, len(input), self._batch_size)]
        out = []
        for texts in text_batch:
            item: Dict = {'inputs': texts}
            if model:
                item['model'] = model
            item.update(extras)
            out.append(item)
        return out

    def _parse_response(self, response: Union[Dict, List], input: Union[List, str]
                        ) -> Union[List[float], List[List[float]], Dict]:
        if isinstance(response, dict):
            if 'data' in response:
                return super()._parse_response(response, input)
            return response
        if isinstance(response, list):
            if not response:
                raise RuntimeError('empty embedding response')
            if isinstance(input, str):
                first = response[0]
                return response if isinstance(first, float) else first
            return response
        raise RuntimeError(f'unexpected embedding response type: {type(response)!r}')


class Qwen3Rerank(LazyLLMOnlineRerankModuleBase):
    _PROMPT_PREFIX = (
        '<|im_start|>system\n'
        'Judge whether the Document meets the requirements based on the Query and the Instruct provided. '
        'Note that the answer can only be "yes" or "no".'
        '<|im_end|>\n<|im_start|>user\n'
    )
    _PROMPT_SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'

    _QUERY_TEMPLATE = '{prefix}<Instruct>: {instruction}\n<Query>: {query}\n'
    _DOCUMENT_TEMPLATE = '<Document>: {doc}{suffix}'

    _LOCAL_TRUNCATE_MAX_CHARS = 16384
    _DEFAULT_TASK_DESCRIPTION = 'Given a web search query, retrieve relevant passages that answer the query'

    def __init__(
        self,
        embed_model_name: str = 'Qwen3Reranker',
        embed_url: Optional[str] = None,
        api_key: str = 'api_key',
        batch_size: int = 64,
        truncate_text: bool = True,
        output_format: Optional[str] = None,
        join: Union[bool, str] = False,
        task_description: Optional[str] = None,
        request_timeout: Optional[float] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            task_description: 任务描述，会被拼入 system/user 区块。
        """
        super().__init__(model_series='qwen', embed_url=embed_url, api_key=api_key, embed_model_name=embed_model_name)
        if not embed_url:
            raise ValueError('`url` 不能为空，请传入远端重排序服务地址。')

        self._url = embed_url
        # self._api_key = api_key
        self._batch_size = max(1, int(batch_size))
        self._truncate_text = bool(truncate_text)
        # 兼容旧参数名 timeout；优先使用 request_timeout
        self._timeout = request_timeout if request_timeout is not None else timeout

        self._headers: Dict[str, str] = self._build_headers()
        self._session = requests.Session()
        self._task_description = task_description or self._DEFAULT_TASK_DESCRIPTION

    def _build_headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self._api_key}',
        }

    def _extract_top_k(self, total: int, **kwargs: Any) -> int:
        top_k = kwargs.get('top_k', kwargs.get('topk', total))
        try:
            top_k = int(top_k)
        except Exception:
            top_k = total
        return max(0, min(top_k, total))

    def _get_format_content(self, nodes: List[DocNode], **kwargs: Any) -> List[str]:
        template: Optional[str] = dict(kwargs).pop('template', None)
        if not template:
            return [n.get_text(metadata_mode=MetadataMode.EMBED) for n in nodes]

        placeholders = re.findall(r'{(\w+)}', template)

        formatted: List[str] = []
        for node in nodes:
            values = {
                key: (
                    node.text
                    if key == 'text'
                    else node.metadata.get(key, '') or node.global_metadata.get(key, '')
                )
                for key in placeholders
            }
            try:
                formatted.append(template.format(**values))
            except Exception as exc:
                LOG.warning('Template formatting failed; fallback to raw text: %s', exc)
                formatted.append(node.get_text(metadata_mode=MetadataMode.EMBED))
        return formatted

    def _build_instruct(self, task_description: str, query: str) -> str:
        """拼装包含系统前缀与用户区块的 query 字符串。"""
        return self._QUERY_TEMPLATE.format(
            prefix=self._PROMPT_PREFIX, instruction=task_description, query=query
        )

    def _build_documents(self, texts: List[str]) -> List[str]:
        """
        将每条文本套入文档模板；若开启 truncate，则在这里进行**本地字符级截断**。
        - 截断阈值：_LOCAL_TRUNCATE_MAX_CHARS
        - 仅当 self._truncate_text 为 True 时生效
        """
        docs: List[str] = []

        def _truncate_if_needed(s: str) -> str:
            if not self._truncate_text:
                return s
            if len(s) <= self._LOCAL_TRUNCATE_MAX_CHARS:
                return s
            return s[: self._LOCAL_TRUNCATE_MAX_CHARS]

        for t in texts:
            t_norm = _truncate_if_needed(t or '')
            docs.append(self._DOCUMENT_TEMPLATE.format(doc=t_norm, suffix=self._PROMPT_SUFFIX))
        return docs

    def _encapsulated_data(self, query: str, texts: List[str], **kwargs: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'query': self._build_instruct(self._task_description, query),
            'documents': self._build_documents(texts),
        }
        if kwargs:
            for k, v in kwargs.items():
                if k not in ('query', 'documents'):
                    payload[k] = v
        return payload

    def _parse_response(self, response: Any) -> List[float]:
        """
        期望输入：
            {"results": [{"index": int, "relevance_score": float}, ...]}
        """
        if not isinstance(response, dict) or 'results' not in response:
            LOG.warning("response missing 'results' field: %r", response)
            return []

        results = response.get('results', [])
        try:
            results = sorted(results, key=lambda x: x['index'])
            return [float(item['relevance_score']) for item in results]
        except Exception as exc:
            LOG.error('Failed to parse response: %s; response=%r', exc, response)
            return []

    def forward(self, nodes: List[DocNode], query: str, **kwargs: Any) -> List[DocNode]:
        if not nodes:
            return []

        texts = self._get_format_content(nodes, **kwargs)
        top_k = self._extract_top_k(len(texts), **kwargs)

        all_scores: List[float] = []
        for start in range(0, len(texts), self._batch_size):
            batch_texts = texts[start:start + self._batch_size]
            payload = self._encapsulated_data(query, batch_texts, **kwargs)

            try:
                resp = self._session.post(
                    self._url, json=payload, headers=self._headers, timeout=self._timeout
                )
                resp.raise_for_status()
                scores = self._parse_response(resp.json())
            except requests.RequestException as exc:
                LOG.error('HTTP request for reranking failed (this batch will be scored as 0): %s', exc)
                scores = []

            if len(scores) != len(batch_texts):
                LOG.warning(
                    'Returned scores count mismatches inputs: got=%d, expected=%d; padding with zeros.',
                    len(scores), len(batch_texts),
                )
                if len(scores) < len(batch_texts):
                    scores += [0.0] * (len(batch_texts) - len(scores))
                else:
                    scores = scores[:len(batch_texts)]

            all_scores.extend(scores)

        scored_nodes: List[DocNode] = [nodes[i].with_score(all_scores[i]) for i in range(len(nodes))]
        scored_nodes.sort(key=lambda n: n.relevance_score, reverse=True)
        results = scored_nodes[:top_k] if top_k > 0 else scored_nodes
        LOG.debug(f'Rerank use `{self._embed_model_name}` and get nodes: {results}')
        return results


def get_model(model_name, cfg):
    m = AutoModel(model=model_name, config=cfg)
    return m
