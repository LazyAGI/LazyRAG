import os
import signal
import threading

from lazyllm.tools.rag.parsing_service import DocumentProcessorWorker
from common.db import get_doc_task_db_config

db_config = get_doc_task_db_config()
doc_processor_worker = DocumentProcessorWorker(
    port=int(os.environ.get('LAZYRAG_DOCUMENT_WORKER_PORT', '8001')),
    db_config=db_config,
    num_workers=1,
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
        # NOTE: DocumentProcessorWorker has no public wait(); _worker_impl is internal. May break with lazyllm updates.
        doc_processor_worker._worker_impl.wait()
    except KeyboardInterrupt:
        pass
    # Keep process alive; wait() may return immediately with some launcher configs
    _shutdown_event.wait()
