import os
import signal
import threading

from lazyllm.tools.rag.parsing_service import DocumentProcessorWorker
from common.db import require_shared_db_config


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value and value.strip() else default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name: str) -> list[str] | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return [item.strip() for item in value.split(',') if item.strip()]


db_config = require_shared_db_config('DocumentProcessorWorker')
doc_processor_worker = DocumentProcessorWorker(
    port=_env_int('LAZYRAG_DOCUMENT_WORKER_PORT', 8001),
    db_config=db_config,
    num_workers=_env_int('LAZYRAG_DOCUMENT_WORKER_NUM_WORKERS', 1),
    lease_duration=_env_float('LAZYRAG_DOCUMENT_WORKER_LEASE_DURATION', 300.0),
    lease_renew_interval=_env_float('LAZYRAG_DOCUMENT_WORKER_LEASE_RENEW_INTERVAL', 60.0),
    high_priority_task_types=_env_list('LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_TASK_TYPES'),
    high_priority_only=_env_bool('LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_ONLY', False),
    poll_mode=os.environ.get('LAZYRAG_DOCUMENT_WORKER_POLL_MODE', 'direct'),
)

_shutdown_event = threading.Event()


def _on_signal(signum, frame):
    _shutdown_event.set()
    try:
        doc_processor_worker.stop()
    except Exception:
        pass


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    doc_processor_worker.start()
    try:
        doc_processor_worker.wait()
    except KeyboardInterrupt:
        pass
    # Keep process alive; wait() may return immediately with some launcher configs
    _shutdown_event.wait()
