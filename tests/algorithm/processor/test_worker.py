import importlib
import runpy
import signal
import sys


class _FakeDocumentProcessorWorker:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.waited = False
        self.stopped = False
        _FakeDocumentProcessorWorker.instances.append(self)

    def start(self):
        self.started = True

    def wait(self):
        self.waited = True

    def stop(self):
        self.stopped = True


def _fresh_import_worker(monkeypatch):
    from lazyllm.tools.rag import parsing_service
    import processor.db

    _FakeDocumentProcessorWorker.instances = []
    monkeypatch.setattr(parsing_service, 'DocumentProcessorWorker', _FakeDocumentProcessorWorker)
    monkeypatch.setattr(processor.db, 'require_shared_db_config', lambda service_name: {'service': service_name})
    sys.modules.pop('processor.worker', None)
    return importlib.import_module('processor.worker')


def test_worker_constructs_document_processor_worker_from_env(monkeypatch):
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_PORT', '8124')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_NUM_WORKERS', '3')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_LEASE_DURATION', '12.5')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_LEASE_RENEW_INTERVAL', '2.5')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_TASK_TYPES', 'parse, index')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_ONLY', 'yes')
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_POLL_MODE', 'queue')

    module = _fresh_import_worker(monkeypatch)

    assert module.db_config == {'service': 'DocumentProcessorWorker'}
    assert module.doc_processor_worker is _FakeDocumentProcessorWorker.instances[0]
    assert module.doc_processor_worker.kwargs == {
        'port': 8124,
        'db_config': {'service': 'DocumentProcessorWorker'},
        'num_workers': 3,
        'lease_duration': 12.5,
        'lease_renew_interval': 2.5,
        'high_priority_task_types': ['parse', 'index'],
        'high_priority_only': True,
        'poll_mode': 'queue',
    }


def test_worker_signal_handler_sets_shutdown_and_stops_worker(monkeypatch):
    module = _fresh_import_worker(monkeypatch)

    module._on_signal(None, None)

    assert module._shutdown_event.is_set()
    assert module.doc_processor_worker.stopped is True


def test_worker_signal_handler_ignores_stop_errors(monkeypatch):
    module = _fresh_import_worker(monkeypatch)

    class BrokenWorker:
        def stop(self):
            raise RuntimeError('stop failed')

    module.doc_processor_worker = BrokenWorker()

    module._on_signal(None, None)

    assert module._shutdown_event.is_set()


def test_worker_main_starts_waits_and_registers_signals(monkeypatch):
    from lazyllm.tools.rag import parsing_service
    import processor.db
    import threading

    _FakeDocumentProcessorWorker.instances = []
    signal_calls = []

    class FakeEvent:
        def __init__(self):
            self.waited = False

        def set(self):
            return None

        def is_set(self):
            return False

        def wait(self):
            self.waited = True
            return None

    monkeypatch.setattr(parsing_service, 'DocumentProcessorWorker', _FakeDocumentProcessorWorker)
    monkeypatch.setattr(processor.db, 'require_shared_db_config', lambda service_name: {'service': service_name})
    monkeypatch.setattr(threading, 'Event', FakeEvent)
    monkeypatch.setattr(signal, 'signal', lambda sig, handler: signal_calls.append((sig, handler.__name__)))
    monkeypatch.setenv('LAZYRAG_DOCUMENT_WORKER_PORT', '8126')
    sys.modules.pop('processor.worker', None)

    runpy.run_module('processor.worker', run_name='__main__')

    instance = _FakeDocumentProcessorWorker.instances[0]
    assert instance.started is True
    assert instance.waited is True
    assert (signal.SIGTERM, '_on_signal') in signal_calls
    assert (signal.SIGINT, '_on_signal') in signal_calls


def test_worker_main_handles_keyboard_interrupt_from_wait(monkeypatch):
    from lazyllm.tools.rag import parsing_service
    import processor.db
    import threading

    signal_calls = []

    class InterruptingDocumentProcessorWorker(_FakeDocumentProcessorWorker):
        def wait(self):
            self.waited = True
            raise KeyboardInterrupt

    class FakeEvent:
        def set(self):
            return None

        def wait(self):
            return None

    monkeypatch.setattr(parsing_service, 'DocumentProcessorWorker', InterruptingDocumentProcessorWorker)
    monkeypatch.setattr(processor.db, 'require_shared_db_config', lambda service_name: {'service': service_name})
    monkeypatch.setattr(threading, 'Event', FakeEvent)
    monkeypatch.setattr(signal, 'signal', lambda sig, handler: signal_calls.append((sig, handler.__name__)))
    sys.modules.pop('processor.worker', None)

    runpy.run_module('processor.worker', run_name='__main__')

    assert signal_calls
