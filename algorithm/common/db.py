"""Parse database URL into LazyLLM SqlManager db_config (db_type, user, password, host, port, db_name)."""
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse, unquote


def parse_db_url(url: Optional[str]) -> Optional[Dict[str, Any]]:
    """Convert postgresql+psycopg://user:password@host:port/dbname into SqlManager kwargs."""
    if not url or not url.strip():
        return None
    try:
        u = urlparse(url)
        if not u.hostname:
            return None
        # support postgresql+psycopg:// or postgresql://
        db_type = (u.scheme or 'postgresql').split('+')[0]
        if db_type not in ('postgresql', 'mysql', 'mssql', 'sqlite', 'mysql+pymysql', 'tidb'):
            db_type = 'postgresql'
        return {
            'db_type': db_type,
            'user': unquote(u.username) if u.username else '',
            'password': unquote(u.password) if u.password else '',
            'host': u.hostname or '',
            'port': u.port or (5432 if 'postgres' in db_type else 3306),
            'db_name': (u.path or '/').lstrip('/') or 'app',
        }
    except Exception:
        return None


def get_doc_task_db_config() -> Optional[Dict[str, Any]]:
    """Get db_config from DOC_TASK_DATABASE_URL for DocumentProcessor / DocumentProcessorWorker."""
    url = os.getenv('LAZYRAG_DOC_TASK_DATABASE_URL')
    return parse_db_url(url)
