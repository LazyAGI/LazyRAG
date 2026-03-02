import os
import sys

# ensure project root (algorithm/) is on path when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazyllm.tools.rag.parsing_service import DocumentProcessor  # noqa: E402

from common.db import get_doc_task_db_config  # noqa: E402

db_config = get_doc_task_db_config()
doc_processor = DocumentProcessor(
    port=int(os.environ.get('DOCUMENT_PROCESSOR_PORT', '8000')),
    db_config=db_config,
    num_workers=0,  # use separate worker container
)

if __name__ == '__main__':
    doc_processor.start()
