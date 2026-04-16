import importlib
import sys


class _FakeDocumentProcessor:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.waited = False
        self.stopped = False
        _FakeDocumentProcessor.instances.append(self)

    def start(self):
        self.started = True

    def wait(self):
        self.waited = True

    def stop(self):
        self.stopped = True


def _fresh_import_server(monkeypatch):
    from lazyllm.tools.rag import parsing_service
    import processor.db

    _FakeDocumentProcessor.instances = []
    monkeypatch.setattr(parsing_service, 'DocumentProcessor', _FakeDocumentProcessor)
    monkeypatch.setattr(processor.db, 'require_shared_db_config', lambda service_name: {'service': service_name})
    sys.modules.pop('processor.server', None)
    return importlib.import_module('processor.server')


def test_server_constructs_document_processor_from_env(monkeypatch):
    monkeypatch.setenv('LAZYRAG_DOCUMENT_PROCESSOR_PORT', '8123')

    module = _fresh_import_server(monkeypatch)

    assert module.db_config == {'service': 'DocumentProcessor'}
    assert module.doc_processor is _FakeDocumentProcessor.instances[0]
    assert module.doc_processor.kwargs == {
        'port': 8123,
        'db_config': {'service': 'DocumentProcessor'},
        'num_workers': 0,
    }


def test_server_signal_handler_sets_shutdown_and_stops_processor(monkeypatch):
    module = _fresh_import_server(monkeypatch)

    module._on_signal(None, None)

    assert module._shutdown_event.is_set()
    assert module.doc_processor.stopped is True
