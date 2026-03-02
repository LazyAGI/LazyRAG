import os
from lazyllm.tools.rag import DocumentProcessorWorker

_db_url = os.getenv("DOC_TASK_DATABASE_URL")
db_config = {"url": _db_url} if _db_url else None
doc_processor_worker = DocumentProcessorWorker(
    port=int(os.environ.get("DOCUMENT_WORKER_PORT", "8001")),
    db_config=db_config,
)

if __name__ == "__main__":
    doc_processor_worker.start()