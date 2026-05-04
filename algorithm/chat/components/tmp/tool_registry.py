from typing import Dict, Any
from abc import ABC, abstractmethod
import os

DOCUMENT_URL = os.getenv('LAZYLLM_DOCUMENT_URL', 'http://127.0.0.1:8525')


class BaseTool(ABC):
    @property
    @abstractmethod
    def tool_schema(self) -> Dict[str, Any]:
        """Tool schema describing the tool's functionality and parameters.

        Returns:
            Dict[str, Any]: Tool schema dict in the format:
            {
                'tool_name': {
                    'description': 'tool description',
                    'parameters': {
                        'param_name': {
                            'type': 'parameter type',
                            'des': 'parameter description'
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
        """Return the tool name; defaults to the first key in the schema."""
        if self.tool_schema:
            return list(self.tool_schema.keys())[0]
        return self.__class__.__name__.lower()


# Tool registry: automatically collects instances of all BaseTool subclasses
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
