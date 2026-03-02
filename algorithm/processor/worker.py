import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazyllm.tools.rag.parsing_service import DocumentProcessorWorker  # noqa: E402

from common.db import get_doc_task_db_config  # noqa: E402

db_config = get_doc_task_db_config()
doc_processor_worker = DocumentProcessorWorker(
    port=int(os.environ.get('LAZYRAG_DOCUMENT_WORKER_PORT', '8001')),
    db_config=db_config,
    num_workers=1,
)

if __name__ == '__main__':
    doc_processor_worker.start()
