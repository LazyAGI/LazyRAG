"""vocab/db.py: PostgreSQL helpers for lazyrag_vocab table.

Table schema (auto-created on first use):

    CREATE TABLE lazyrag_vocab (
        id             SERIAL      PRIMARY KEY,
        word           TEXT        NOT NULL,
        group_id       TEXT        NOT NULL,   -- maps to cluster_id in AC processor
        description    TEXT,
        source         TEXT        DEFAULT '用户',
        reference      TEXT,
        create_user_id TEXT        NOT NULL DEFAULT '',
        create_time    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        update_time    TIMESTAMP
    );

Environment variable:
    LAZYRAG_DATABASE_URL  PostgreSQL URL, e.g. postgresql://user:pass@host:5432/db
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from lazyllm import LOG

VOCAB_TABLE = 'lazyrag_vocab'
_DB_URL_ENV = 'LAZYRAG_DATABASE_URL'

_DDL_TABLE = f"""
CREATE TABLE IF NOT EXISTS {VOCAB_TABLE} (
    id             SERIAL      PRIMARY KEY,
    word           TEXT        NOT NULL,
    group_id       TEXT        NOT NULL,
    description    TEXT,
    source         TEXT        DEFAULT '用户',
    reference      TEXT,
    create_user_id TEXT        NOT NULL DEFAULT '',
    create_time    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time    TIMESTAMP
)
"""
_DDL_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{VOCAB_TABLE}_user_id
    ON {VOCAB_TABLE}(create_user_id)
"""

_table_ensured = False
_table_ensure_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_db_url() -> Optional[str]:
    value = os.getenv(_DB_URL_ENV)
    return value if value and value.strip() else None


def _parse_pg_url(url: str) -> Dict[str, Any]:
    u = urlparse(url)
    return dict(
        host=u.hostname or 'localhost',
        port=u.port or 5432,
        dbname=(u.path or '/').lstrip('/') or 'app',
        user=unquote(u.username or ''),
        password=unquote(u.password or ''),
    )


def _get_conn():
    """Open a psycopg2 connection using LAZYRAG_DATABASE_URL."""
    import psycopg2  # noqa: PLC0415  (imported here to avoid hard dep at module load)
    url = _get_db_url()
    if not url:
        raise RuntimeError(
            f'[VocabDB] {_DB_URL_ENV} is not set; cannot connect to database.'
        )
    return psycopg2.connect(**_parse_pg_url(url))


# ---------------------------------------------------------------------------
# Table bootstrap
# ---------------------------------------------------------------------------

def ensure_vocab_table() -> None:
    """Create lazyrag_vocab + index if they do not exist (idempotent)."""
    url = _get_db_url()
    if not url:
        LOG.warning('[VocabDB] %s not set; skipping table init.', _DB_URL_ENV)
        return
    try:
        conn = _get_conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_DDL_TABLE)
            cur.execute(_DDL_INDEX)
        conn.close()
        LOG.info('[VocabDB] table %s ensured.', VOCAB_TABLE)
    except Exception as exc:
        LOG.error('[VocabDB] ensure_vocab_table failed: %s', exc)


def _ensure_table_once() -> None:
    """Call ensure_vocab_table exactly once per process."""
    global _table_ensured
    if not _table_ensured:
        with _table_ensure_lock:
            if not _table_ensured:
                ensure_vocab_table()
                _table_ensured = True


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

def fetch_vocab_for_user(user_id: str) -> List[Dict[str, Any]]:
    """Return all vocab rows for *user_id* as a list of ``{'word': ..., 'cluster_id': ...}`` dicts.

    Returns an empty list when the DB is unavailable or user has no entries.
    The ``cluster_id`` key matches the default ``cluster_key`` of
    :class:`lazyllm.tools.rag.QueryEnhACProcessor`.
    """
    _ensure_table_once()
    url = _get_db_url()
    if not url:
        LOG.warning('[VocabDB] %s not set; returning empty vocab for user=%r.', _DB_URL_ENV, user_id)
        return []
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT word, group_id FROM {VOCAB_TABLE} WHERE create_user_id = %s',
                (user_id,),
            )
            rows = cur.fetchall()
        conn.close()
        result = [{'word': r[0], 'cluster_id': r[1]} for r in rows]
        LOG.info('[VocabDB] fetched %d vocab entries for user=%r.', len(result), user_id)
        return result
    except Exception as exc:
        LOG.error('[VocabDB] fetch_vocab_for_user(%r) failed: %s', user_id, exc)
        return []
