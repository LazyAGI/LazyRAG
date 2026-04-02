import re
import itertools
from typing import Tuple, List
from lazyllm.tools.rag import DocNode

from chat.utils.url import is_valid_path, get_url_basename


def shorten_image_urls(markdown: str) -> Tuple[str, List[str]]:
    """Replace remote image URLs in Markdown with local filenames **and**
    return the list of matched original image links.

    Parameters
    ----------
    markdown : str
        A string containing Markdown content.

    Returns
    -------
    Tuple[str, List[str]]
        * The Markdown string with image URLs converted to local filenames.
        * A list of all matched (original) image URLs found in the input.

    Example
    -------
    >>> new_md, urls = shorten_image_urls("![alt](https://example.com/pic.png?foo)")
    >>> new_md
    '![alt](pic.png)'
    >>> urls
    ['https://example.com/pic.png?foo']
    """

    pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    matched_urls: List[str] = []

    def _replace(match: re.Match) -> str:
        alt_text, url = match.groups()
        if is_valid_path(url):
            matched_urls.append(url)
            filename = get_url_basename(url)
            return f'![{alt_text}]({filename})'
        else:
            return match.group(0)

    new_markdown = pattern.sub(_replace, markdown)
    return new_markdown, matched_urls


class AggregateComponent:
    def __init__(self, top_k: int = 0):
        self.top_k = top_k

    def __call__(self, nodes, **kwargs) -> List[DocNode]:
        """Run component."""
        # 处理空列表
        if not nodes:
            return nodes

        result_nodes = []
        nodes = sorted(nodes, key=lambda x: x.global_metadata['docid'])
        for _, group in itertools.groupby(nodes, key=lambda x: x.global_metadata['docid']):
            grouped_nodes = sorted(group, key=lambda x: (x.metadata.get('index') or 0))

            # 合并节点内容
            content = []
            all_images = []
            table_image_map = {}
            for node in grouped_nodes:
                text = node._content
                title = node.metadata.get('title', '')
                if title:
                    text = f'{title.strip()}\n{text.lstrip()}'
                node_str, images = shorten_image_urls(text)
                content.append(node_str)
                all_images.extend(images)
                if node.metadata.get('table_image_map', None):
                    table_image_map.update(node.metadata['table_image_map'])
            content = f"\n\n{'---'}\n\n".join(content)

            first_node = grouped_nodes[0]
            # 创建新节点
            metadata = {'images': all_images}
            metadata.update(first_node._metadata)
            if table_image_map:
                metadata['table_image_map'] = table_image_map
            aggregate_node = DocNode(
                uid=first_node._uid,
                group=first_node._group,
                text=content,
                metadata=metadata,
                global_metadata=first_node.global_metadata
            )
            aggregate_node.excluded_embed_metadata_keys = first_node.excluded_embed_metadata_keys
            aggregate_node.excluded_llm_metadata_keys = first_node.excluded_llm_metadata_keys
            result_nodes.append(aggregate_node)
        return result_nodes
