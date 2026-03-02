import os
from lazyllm.tools.rag import DocumentProcessor

_db_url = os.getenv("DOC_TASK_DATABASE_URL")
db_config = {"url": _db_url} if _db_url else None
doc_processor = DocumentProcessor(
    port=int(os.environ.get("DOCUMENT_PROCESSOR_PORT", "8000")),
    db_config=db_config,
)

if __name__ == "__main__":
    doc_processor.start()