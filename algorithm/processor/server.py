import os

from lazyllm.tools.rag.parsing_service import DocumentProcessor
from common.db import get_doc_task_db_config

db_config = get_doc_task_db_config()
doc_processor = DocumentProcessor(
    port=int(os.environ.get('LAZYRAG_DOCUMENT_PROCESSOR_PORT', '8000')),
    db_config=db_config,
    num_workers=0,  # use separate worker container
)

if __name__ == '__main__':
    doc_processor.start().wait()
