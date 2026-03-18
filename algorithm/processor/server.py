import os
import signal
import threading

from lazyllm.tools.rag.parsing_service import DocumentProcessor
from common.db import require_shared_db_config


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value and value.strip() else default


db_config = require_shared_db_config('DocumentProcessor')
doc_processor = DocumentProcessor(
    port=_env_int('LAZYRAG_DOCUMENT_PROCESSOR_PORT', 8000),
    db_config=db_config,
    num_workers=0,  # use separate worker container
)

_shutdown_event = threading.Event()
def _on_signal(signum, frame):
    _shutdown_event.set()
    try:
        doc_processor.stop()
    except Exception:
        pass


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    doc_processor.start()
    try:
        doc_processor.wait()
    except KeyboardInterrupt:
        pass
    # Keep process alive; wait() may return immediately with some launcher configs
    _shutdown_event.wait()
