from typing import List, Dict, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import copy
import os
import itertools
import lazyllm
from lazyllm.tools.rag import Retriever
from chat.chat_pipelines.naive import get_ppl_search

DOCUMENT_URL = os.getenv('LAZYLLM_DOCUMENT_URL', 'http://127.0.0.1:8525')


class BaseTool(ABC):
    """工具基类，要求所有工具类都必须定义 tool_schema 和 __call__"""

    @property
    @abstractmethod
    def tool_schema(self) -> Dict[str, Any]:
        """
        工具 schema，描述工具的功能和参数

        Returns:
            Dict[str, Any]: 工具 schema 字典，格式为:
            {
                'tool_name': {
                    'description': '工具描述',
                    'parameters': {
                        'param_name': {
                            'type': '参数类型',
                            'des': '参数描述'
                        }
                    }
                }
            }
        """
        pass

    @abstractmethod
    def __call__(self, *args, **kwargs) -> Any:
        """
        执行工具调用，子类必须实现。

        Returns:
            Any: 工具执行结果
        """
        pass

    @property
    def tool_name(self) -> str:
        """返回工具名称，默认使用 schema 中的第一个 key"""
        if self.tool_schema:
            return list(self.tool_schema.keys())[0]
        return self.__class__.__name__.lower()


# input querys original_query document_url  params  return: list of content
@dataclass
class KBSearchMemory:
    """KBSearch 工具的内存结构"""
    nodes: list = field(default_factory=list)
    relevant_nodes: list = field(default_factory=list)
    agg_nodes: dict = field(default_factory=dict)


class KBSearch(BaseTool):
    """知识库检索工具类"""

    def __call__(self, querys,  static_params, file_names=None):
        return self.chunk_search(querys=querys, file_names=file_names, static_params=static_params)

    @property
    def tool_schema(self) -> Dict[str, Any]:
        """工具 schema 定义"""
        return {
            'kb_search': {
                'description': 'Used to retrieve content chunks from the knowledge \
                    base and extract target information points. Supports global and document-scoped search.',
                'parameters': {
                    'querys': {
                        'type': 'List[str]',
                        'des': 'Distinct semantic queries; avoid overlap.'
                    },
                    'file_names': {
                        'type': 'Optional[List[str]] = None',
                        'des': 'Restrict search to specific documents; None means global.'
                    }
                }
            }
        }

    def chunk_search(
        self,
        querys: List[str],
        file_names: List[str] = None,
        static_params: dict = None,
    ) -> List[str]:
        """执行文档块检索"""
        if static_params is None:
            static_params = {}

        original_query = static_params.get('query', '')
        document_url = static_params.get('document_url', DOCUMENT_URL)

        if file_names:
            file_ids = self.file_search(file_names, static_params)
        else:
            file_ids = None

        search_ppl = get_ppl_search(url=document_url)

        node_ids = set()
        params = copy.deepcopy(static_params)

        file_names_unique = set()
        unique_nodes = []

        for query in querys:
            if file_ids:
                params['filters'].update({'docid': file_ids})
            nodes = search_ppl(params | {'query': query})
            for node in nodes:
                if node._uid not in node_ids:
                    file_names_unique.add(node.global_metadata.get('file_name', ''))
                    node_ids.add(node._uid)
                    unique_nodes.append(node)
        if file_ids:
            original_nodes = search_ppl(params | {'query': original_query})
            for node in original_nodes:
                if node._uid not in node_ids:
                    file_names_unique.add(node.global_metadata.get('file_name', ''))
                    node_ids.add(node._uid)
                    unique_nodes.append(node)

        nodes = []
        for _, grp in itertools.groupby(unique_nodes, key=lambda x: x.global_metadata['docid']):
            grouped_nodes = list(grp)
            new_node = grouped_nodes[0]
            grouped_nodes = sorted(grouped_nodes, key=lambda x: x.metadata.get('index', 0))
            contents = [
                '{}\n{}'.format(node.metadata.get('title', '').strip(), node.get_text())
                for node in grouped_nodes
            ]
            new_node._content = '\n'.join(contents)
            nodes.append(new_node)

        res = []
        for node in nodes:
            filename = node.metadata.get('file_name', '')
            res.append(f'file_name: {filename}\n{node.get_text()}')

        return nodes, res

    def file_search(self, file_names: List[str], static_params: dict = None, topk: int = 3) -> List[str]:
        filters = static_params.get('filters', {}) if static_params else {}
        document_url = static_params.get('document_url', DOCUMENT_URL) if static_params else DOCUMENT_URL
        name = static_params.get('name', '__default__')
        doc = lazyllm.Document(url=f'{document_url}/_call', name=name)
        retriever = Retriever(doc, group_name='filename', embed_keys=['bge_m3_sparse'], topk=topk)

        file_ids = []
        for file_name in file_names:
            nodes = retriever(file_name, filters=filters)
            for node in nodes:
                docid = node.global_metadata.get('docid', '')
                if docid and docid not in file_ids:
                    file_ids.append(docid)
        return file_ids


# 工具注册表：自动收集所有 BaseTool 子类的实例
_tool_instances: Dict[str, BaseTool] = {}
_tool_schemas: Dict[str, Dict[str, Any]] = {}


def register_tool(tool_name: str, tool_instance: BaseTool):
    """
    注册工具实例

    Args:
        tool_name: 工具名称
        tool_instance: 工具实例（必须是 BaseTool 的子类）
    """
    if not isinstance(tool_instance, BaseTool):
        raise TypeError(f'Tool instance must be a subclass of BaseTool, got {type(tool_instance)}')
    _tool_instances[tool_name] = tool_instance
    _tool_schemas[tool_name] = tool_instance.tool_schema


def get_all_tool_schemas() -> Dict[str, Dict[str, Any]]:
    """
    获取所有已注册工具的 schema

    Returns:
        Dict[str, Dict[str, Any]]: 所有工具的 schema 字典
    """
    return _tool_schemas.copy()


def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    """
    获取指定工具的 schema

    Args:
        tool_name: 工具名称

    Returns:
        Dict[str, Any]: 工具的 schema 字典
    """
    if tool_name not in _tool_schemas:
        raise KeyError(f'Tool {tool_name!r} not found in registry')
    return _tool_schemas[tool_name]


def get_tool_instance(tool_name: str) -> BaseTool:
    """
    获取指定工具的实例

    Args:
        tool_name: 工具名称

    Returns:
        BaseTool: 工具实例
    """
    if tool_name not in _tool_instances:
        raise KeyError(f'Tool {tool_name!r} not found in registry')
    return _tool_instances[tool_name]


register_tool('kb_search', KBSearch())
