import os
import signal
import threading

from lazyllm.tools.rag.parsing_service import DocumentProcessorWorker
from common.db import require_shared_db_config
from common.env import env_bool, env_float, env_int, env_list


db_config = require_shared_db_config('DocumentProcessorWorker')
doc_processor_worker = DocumentProcessorWorker(
    port=env_int('LAZYRAG_DOCUMENT_WORKER_PORT', 8001),
    db_config=db_config,
    num_workers=env_int('LAZYRAG_DOCUMENT_WORKER_NUM_WORKERS', 1),
    lease_duration=env_float('LAZYRAG_DOCUMENT_WORKER_LEASE_DURATION', 300.0),
    lease_renew_interval=env_float('LAZYRAG_DOCUMENT_WORKER_LEASE_RENEW_INTERVAL', 60.0),
    high_priority_task_types=env_list('LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_TASK_TYPES'),
    high_priority_only=env_bool('LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_ONLY', False),
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
