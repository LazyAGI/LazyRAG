"""Helpers for converting the shared PostgreSQL URL into LazyLLM SqlManager db_config."""
import os
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse


SHARED_DB_ENV_KEY = 'LAZYRAG_DATABASE_URL'


def parse_db_url(url: Optional[str]) -> Optional[Dict[str, Any]]:
    """Convert postgresql+psycopg://user:password@host:port/dbname into SqlManager kwargs."""
    if not url or not url.strip():
        return None
    try:
        u = urlparse(url)
        db_type = (u.scheme or 'postgresql').split('+')[0]
        if db_type != 'postgresql':
            return None
        if not u.hostname:
            return None
        return {
            'db_type': 'postgresql',
            'user': unquote(u.username) if u.username else '',
            'password': unquote(u.password) if u.password else '',
            'host': u.hostname or '',
            'port': u.port or 5432,
            'db_name': (u.path or '/').lstrip('/') or 'app',
        }
    except (ValueError, AttributeError, TypeError):
        return None


def get_shared_database_url() -> Optional[str]:
    """Return the shared PostgreSQL URL configured by docker-compose."""
    value = os.getenv(SHARED_DB_ENV_KEY)
    return value if value and value.strip() else None


def get_shared_db_config() -> Optional[Dict[str, Any]]:
    """Get db_config for DocServer / DocumentProcessor / Worker from the shared DB env."""
    return parse_db_url(get_shared_database_url())


def require_shared_db_config(service_name: str) -> Dict[str, Any]:
    """Return shared db_config or raise a clear error when it is missing."""
    db_config = get_shared_db_config()
    if db_config is None:
        raise RuntimeError(
            f'{service_name} requires a shared database configuration. '
            f'Set {SHARED_DB_ENV_KEY} to a valid PostgreSQL URL.'
        )
    return db_config


def get_doc_task_db_config() -> Optional[Dict[str, Any]]:
    """Backward-compatible alias for the shared database config."""
    return get_shared_db_config()
