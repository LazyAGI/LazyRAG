import pytest

import chat.components.tmp.tool_registry as registry
from chat.components.tmp.tool_registry import BaseTool


class _DummyTool(BaseTool):
    @property
    def tool_schema(self):
        return {
            'demo_tool': {
                'description': 'demo',
                'parameters': {
                    'name': {'type': 'string', 'des': 'name'},
                },
            }
        }

    def __call__(self, *args, **kwargs):
        return {'args': args, 'kwargs': kwargs}


def test_base_tool_name_uses_schema_key():
    tool = _DummyTool()

    assert tool.tool_name == 'demo_tool'


def test_register_and_get_tool_schema_and_instance(monkeypatch):
    monkeypatch.setattr(registry, '_tool_instances', {})
    monkeypatch.setattr(registry, '_tool_schemas', {})
    tool = _DummyTool()

    registry.register_tool('demo_tool', tool)

    schemas = registry.get_all_tool_schemas()
    assert 'demo_tool' in schemas
    assert registry.get_tool_schema('demo_tool')['demo_tool']['description'] == 'demo'
    assert registry.get_tool_instance('demo_tool') is tool


def test_register_tool_rejects_invalid_type(monkeypatch):
    monkeypatch.setattr(registry, '_tool_instances', {})
    monkeypatch.setattr(registry, '_tool_schemas', {})

    with pytest.raises(TypeError, match='subclass of BaseTool'):
        registry.register_tool('bad', object())


def test_register_tool_overwrites_existing_name(monkeypatch):
    monkeypatch.setattr(registry, '_tool_instances', {})
    monkeypatch.setattr(registry, '_tool_schemas', {})
    first = _DummyTool()
    second = _DummyTool()

    registry.register_tool('demo_tool', first)
    registry.register_tool('demo_tool', second)

    assert registry.get_tool_instance('demo_tool') is second


def test_get_tool_schema_and_instance_raise_for_missing(monkeypatch):
    monkeypatch.setattr(registry, '_tool_instances', {})
    monkeypatch.setattr(registry, '_tool_schemas', {})

    with pytest.raises(KeyError, match='not found in registry'):
        registry.get_tool_schema('missing')
    with pytest.raises(KeyError, match='not found in registry'):
        registry.get_tool_instance('missing')
