from typing import AsyncIterator, AsyncGenerator, Dict, List, Tuple
from lazyllm import ModuleBase

from chat.utils.stream_scanner import BasePlugin, CitationPlugin, ImagePlugin, IncrementalScanner
from chat.utils.url import get_url_basename

# ============================================================
# CustomOutputParser
# ============================================================


class CustomOutputParser(ModuleBase):
    def __init__(self, return_trace: bool = False, llm_type_think: bool = False, **kwargs):
        # image_rewrite_fn: Optional callable(url) -> new_url
        super().__init__(return_trace=return_trace, **kwargs)
        self.llm_type_think = llm_type_think

    # ---------- 公共输出包装 ----------
    def text_with_reference(
        self,
        *,
        think: str | None = None,
        text: str | None = None,
        reference: List[Dict[str, str]] | None = None,
    ) -> Dict[str, object]:
        return {'think': think, 'text': text, 'sources': reference or []}

    def create_source_node(self, index: int, node) -> Dict[str, str]:
        gm = node.global_metadata
        metadata = node.metadata
        return {
            'index': index,
            'number': metadata.get('store_num') or metadata.get('lazyllm_store_num') or -1,
            'docid': gm.get('docid', 'file_id_example'),
            'page': metadata.get('page', -1),
            'bbox': metadata.get('bbox', []),
            'kb_id': gm.get('kb_id', 'kb_id_example'),
            'file_name': gm.get('file_name', 'title_example'),
            'id': node._uid,
            'text': node.text,
            'group': node._group
        }

    # ================== 同步 ==================
    def _extract_citations(self, text: str, refs: Dict[int, Dict[str, str]], image_files: Dict[str, str]):
        refs = {index: self._replace_table_to_image(node) for index, node in refs.items()}
        plugins: List[BasePlugin] = [
            CitationPlugin(refs),
            ImagePlugin(image_files),
        ]
        scn = IncrementalScanner(plugins, initial_state='THINK' if self.llm_type_think else 'BODY')
        output = scn.feed(text) + scn.flush()
        think_parts, text_parts = [], []
        for field, seg in output:
            (think_parts if field == 'think' else text_parts).append(seg)
        return {
            'think': ''.join(think_parts).strip(),
            'text': ''.join(text_parts).strip(),
            'sources': plugins[0].collect(),
        }

    # ================== 流式 ==================
    async def _extract_citations_stream(
        self,
        astream: AsyncIterator[str],
        refs: Dict[int, Dict[str, str]],
        image_files: Dict[str, str]
    ) -> AsyncGenerator[Tuple[str, List[Dict[str, str]]], None]:
        plugins: List[BasePlugin] = [
            CitationPlugin(refs),
            ImagePlugin(image_files),
        ]
        refs = {index: self._replace_table_to_image(node) for index, node in refs.items()}
        scn = IncrementalScanner(plugins, initial_state='THINK' if self.llm_type_think else 'BODY')

        async for chunk in astream:
            for field, seg in scn.feed(chunk):
                yield self.text_with_reference(**{field: seg})

        for field, seg in scn.flush():
            yield self.text_with_reference(**{field: seg})

        metas = plugins[0].collect()
        if metas:
            yield self.text_with_reference(text='', reference=metas)

    def forward(self, input, **kwargs):
        nodes = kwargs.get('aggregate', {})
        if isinstance(nodes, list):
            nodes = {(index + 1): node for index, node in enumerate(nodes)}

        image_files = {}
        for node in nodes.values():
            for url in node.metadata.get('images', []):
                image_files[get_url_basename(url)] = url

        stream = kwargs.get('stream', False)
        if stream:
            generator = self._extract_citations_stream(input, nodes, image_files)
            return generator
        else:
            # 非流式输出，直接生成答案。
            output = self._extract_citations(input, nodes, image_files)
            debug = kwargs.get('debug') or False
            recall_nodes = kwargs.get('recall_result') or []
            recall_nodes = [self.create_source_node(index, node) for index, node in enumerate(recall_nodes)]
            return (output | {'recall': recall_nodes}) if debug else output

    def _replace_table_to_image(self, node):
        metadata = node.metadata
        text = node.text
        if metadata.get('table_image_map', None):
            for content, image_url in metadata['table_image_map'].items():
                text = text.replace(content.strip(), image_url)
        node._content = text
        return node
