import os
import signal
import threading

from lazyllm.tools.rag.parsing_service import DocumentProcessor
from common.db import get_doc_task_db_config

from processor.upload_handler import run_upload_server

db_config = get_doc_task_db_config()
doc_processor = DocumentProcessor(
    port=int(os.environ.get('LAZYRAG_DOCUMENT_PROCESSOR_PORT', '8000')),
    db_config=db_config,
    num_workers=0,  # use separate worker container
)

_shutdown_event = threading.Event()
_upload_server_thread = None


def _on_signal(signum, frame):
    _shutdown_event.set()
    try:
        doc_processor.stop()
    except Exception:
        pass


# (TODO): temp plan, will be removed later
def _run_upload_server_background():
    port = int(os.environ.get('LAZYRAG_UPLOAD_SERVER_PORT', '8001'))
    run_upload_server(port)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # Start upload server in background (for add_doc without doc-manager)
    _upload_server_thread = threading.Thread(target=_run_upload_server_background, daemon=True)
    _upload_server_thread.start()

    doc_processor.start()
    try:
        # NOTE: DocumentProcessor has no public wait(); _impl is internal. May break with lazyllm updates.
        doc_processor._impl.wait()
    except KeyboardInterrupt:
        pass
    # Keep process alive; wait() may return immediately with some launcher configs
    _shutdown_event.wait()
