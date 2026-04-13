from typing import Dict, Any
from abc import ABC, abstractmethod
import os

DOCUMENT_URL = os.getenv('LAZYLLM_DOCUMENT_URL', 'http://127.0.0.1:8525')


class BaseTool(ABC):
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
        pass

    @property
    def tool_name(self) -> str:
        """返回工具名称，默认使用 schema 中的第一个 key"""
        if self.tool_schema:
            return list(self.tool_schema.keys())[0]
        return self.__class__.__name__.lower()


# 工具注册表：自动收集所有 BaseTool 子类的实例
_tool_instances: Dict[str, BaseTool] = {}
_tool_schemas: Dict[str, Dict[str, Any]] = {}


def register_tool(tool_name: str, tool_instance: BaseTool):
    if not isinstance(tool_instance, BaseTool):
        raise TypeError(f'Tool instance must be a subclass of BaseTool, got {type(tool_instance)}')
    _tool_instances[tool_name] = tool_instance
    _tool_schemas[tool_name] = tool_instance.tool_schema


def get_all_tool_schemas() -> Dict[str, Dict[str, Any]]:
    return _tool_schemas.copy()


def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    if tool_name not in _tool_schemas:
        raise KeyError(f'Tool {tool_name!r} not found in registry')
    return _tool_schemas[tool_name]


def get_tool_instance(tool_name: str) -> BaseTool:
    if tool_name not in _tool_instances:
        raise KeyError(f'Tool {tool_name!r} not found in registry')
    return _tool_instances[tool_name]
