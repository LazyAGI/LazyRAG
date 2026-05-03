import importlib
import sys
from types import ModuleType


def test_chat_app_module_uses_create_app_result(monkeypatch):
    sentinel_app = object()
    fake_api = ModuleType('chat.app.api')
    fake_api.create_app = lambda: sentinel_app

    monkeypatch.setitem(sys.modules, 'chat.app.api', fake_api)
    sys.modules.pop('chat.app.chat', None)

    module = importlib.import_module('chat.app.chat')

    assert module.app is sentinel_app
