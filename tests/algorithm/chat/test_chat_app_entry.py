import importlib
import sys
from types import ModuleType


def test_chat_app_module_uses_create_app_result(monkeypatch):
    sentinel_app = object()
    fake_chat_server = ModuleType('chat.app.core.chat_server')
    fake_chat_server.create_app = lambda: sentinel_app

    monkeypatch.setitem(sys.modules, 'chat.app.core.chat_server', fake_chat_server)
    sys.modules.pop('chat.app.chat', None)

    module = importlib.import_module('chat.app.chat')

    assert module.app is sentinel_app
