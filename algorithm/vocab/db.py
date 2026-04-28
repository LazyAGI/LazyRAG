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
import shlex
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from lazyllm import LOG
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

VOCAB_TABLE = 'lazyrag_vocab'
_DB_URL_ENV = 'LAZYRAG_DATABASE_URL'
_CORE_DB_DSN_ENV = 'ACL_DB_DSN'
_CORE_DB_URL_ENV = 'LAZYRAG_CORE_DATABASE_URL'

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
_engine_cache: Dict[str, Engine] = {}
_engine_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_db_url() -> Optional[str]:
    value = os.getenv(_DB_URL_ENV)
    return value if value and value.strip() else None


def _dsn_to_sqlalchemy_url(dsn: str) -> str:
    if '://' in dsn:
        return dsn.strip()
    parts: Dict[str, str] = {}
    for token in shlex.split(dsn):
        if '=' not in token:
            continue
        key, value = token.split('=', 1)
        parts[key.strip()] = value.strip()
    return str(URL.create(
        'postgresql',
        username=parts.get('user') or None,
        password=parts.get('password') or None,
        host=parts.get('host') or 'localhost',
        port=int(parts['port']) if parts.get('port') else 5432,
        database=parts.get('dbname') or parts.get('database') or 'app',
    ))


def _normalize_pg_url(url: Optional[str] = None, dsn: Optional[str] = None) -> str:
    if dsn and dsn.strip():
        return _dsn_to_sqlalchemy_url(dsn)
    if url and url.strip():
        return url.strip()
    raise RuntimeError('postgres connection config is required')


def _get_engine(*, url: Optional[str] = None, dsn: Optional[str] = None) -> Engine:
    engine_url = _normalize_pg_url(url=url, dsn=dsn)
    engine = _engine_cache.get(engine_url)
    if engine is not None:
        return engine
    with _engine_cache_lock:
        engine = _engine_cache.get(engine_url)
        if engine is None:
            engine = create_engine(engine_url, future=True, pool_pre_ping=True)
            _engine_cache[engine_url] = engine
    return engine


def _get_core_db_dsn() -> Optional[str]:
    value = os.getenv(_CORE_DB_DSN_ENV)
    return value if value and value.strip() else None


def _get_core_db_url() -> Optional[str]:
    value = os.getenv(_CORE_DB_URL_ENV)
    return value if value and value.strip() else None


def _get_conn() -> Engine:
    """Return a SQLAlchemy engine using LAZYRAG_DATABASE_URL."""
    url = _get_db_url()
    if not url:
        raise RuntimeError(
            f'[VocabDB] {_DB_URL_ENV} is not set; cannot connect to database.'
        )
    return _get_engine(url=url)


def _get_vocab_conn(db_url: Optional[str] = None) -> Engine:
    return _get_engine(url=db_url or _get_db_url())


def _get_core_conn(*, db_dsn: Optional[str] = None, db_url: Optional[str] = None) -> Engine:
    return _get_engine(
        url=db_url or _get_core_db_url(),
        dsn=db_dsn or _get_core_db_dsn(),
    )


# ---------------------------------------------------------------------------
# Table bootstrap
# ---------------------------------------------------------------------------

def ensure_vocab_table(db_url: Optional[str] = None) -> None:
    """Create lazyrag_vocab + index if they do not exist (idempotent)."""
    url = db_url or _get_db_url()
    if not url:
        LOG.warning('[VocabDB] %s not set; skipping table init.', _DB_URL_ENV)
        return
    try:
        engine = _get_vocab_conn(db_url=url)
        with engine.begin() as conn:
            conn.execute(text(_DDL_TABLE))
            conn.execute(text(_DDL_INDEX))
        LOG.info('[VocabDB] table %s ensured.', VOCAB_TABLE)
    except Exception as exc:
        LOG.error('[VocabDB] ensure_vocab_table failed: %s', exc)


def _ensure_table_once(db_url: Optional[str] = None) -> None:
    """Call ensure_vocab_table exactly once per process."""
    global _table_ensured
    if not _table_ensured:
        with _table_ensure_lock:
            if not _table_ensured:
                ensure_vocab_table(db_url=db_url)
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
        engine = _get_vocab_conn()
        with engine.connect() as conn:
            rows = conn.execute(
                text(f'SELECT word, group_id FROM {VOCAB_TABLE} WHERE create_user_id = :user_id'),
                {'user_id': user_id},
            ).mappings().all()
        result = [{'word': row['word'], 'cluster_id': row['group_id']} for row in rows]
        LOG.info('[VocabDB] fetched %d vocab entries for user=%r.', len(result), user_id)
        return result
    except Exception as exc:
        LOG.error('[VocabDB] fetch_vocab_for_user(%r) failed: %s', user_id, exc)
        return []


def fetch_vocab_groups_for_user(user_id: str, *, db_url: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Return existing vocab groups for a user keyed by ``group_id``."""
    url = db_url or _get_db_url()
    _ensure_table_once(db_url=url)
    if not url:
        LOG.warning('[VocabDB] %s not set; returning empty vocab groups for user=%r.', _DB_URL_ENV, user_id)
        return {}
    try:
        engine = _get_vocab_conn(db_url=url)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""SELECT group_id,
                               word,
                               COALESCE(description, '') AS description,
                               COALESCE(reference, '') AS reference
                        FROM {VOCAB_TABLE}
                        WHERE create_user_id = :user_id
                        ORDER BY group_id, id"""
                ),
                {'user_id': user_id},
            ).mappings().all()
    except Exception as exc:
        LOG.error('[VocabDB] fetch_vocab_groups_for_user(%r) failed: %s', user_id, exc)
        return {}

    groups: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        group_id = row['group_id']
        word = row['word']
        description = row['description']
        reference = row['reference']
        item = groups.setdefault(group_id, {
            'group_id': group_id,
            'description': description or '',
            'words': [],
            'references': [],
        })
        if word and word not in item['words']:
            item['words'].append(word)
        if reference and reference not in item['references']:
            item['references'].append(reference)
        if not item['description'] and description:
            item['description'] = description
    return groups


def list_chat_users(
    *,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db_dsn: Optional[str] = None,
    db_url: Optional[str] = None,
) -> List[str]:
    """Return distinct users who have chat history in the given time range."""
    where = ['c.deleted_at IS NULL']
    params: Dict[str, Any] = {}
    if start_time is not None:
        where.append('h.create_time >= :start_time')
        params['start_time'] = start_time
    if end_time is not None:
        where.append('h.create_time <= :end_time')
        params['end_time'] = end_time
    sql = f"""
        SELECT DISTINCT c.create_user_id
        FROM conversations c
        JOIN chat_histories h ON h.conversation_id = c.id
        WHERE {' AND '.join(where)}
        ORDER BY c.create_user_id
    """
    try:
        engine = _get_core_conn(db_dsn=db_dsn, db_url=db_url)
        with engine.connect() as conn:
            rows = [row for row in conn.execute(text(sql), params).scalars().all() if row]
        return rows
    except Exception as exc:
        LOG.error('[VocabDB] list_chat_users failed: %s', exc)
        return []


def fetch_chat_histories_for_user(
    user_id: str,
    *,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db_dsn: Optional[str] = None,
    db_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return chat histories for one user ordered by time and sequence."""
    params: Dict[str, Any] = {'user_id': user_id}
    where = ['c.create_user_id = :user_id', 'c.deleted_at IS NULL']
    if start_time is not None:
        where.append('h.create_time >= :start_time')
        params['start_time'] = start_time
    if end_time is not None:
        where.append('h.create_time <= :end_time')
        params['end_time'] = end_time
    sql = f"""
        SELECT c.create_user_id,
               c.id AS conversation_id,
               h.id AS message_id,
               h.seq,
               COALESCE(h.raw_content, ''),
               COALESCE(h.content, ''),
               COALESCE(h.result, ''),
               h.create_time
        FROM conversations c
        JOIN chat_histories h ON h.conversation_id = c.id
        WHERE {' AND '.join(where)}
        ORDER BY h.create_time ASC, h.seq ASC, h.id ASC
    """
    try:
        engine = _get_core_conn(db_dsn=db_dsn, db_url=db_url)
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
    except Exception as exc:
        LOG.error('[VocabDB] fetch_chat_histories_for_user(%r) failed: %s', user_id, exc)
        return []

    return [
        {
            'user_id': row['create_user_id'],
            'conversation_id': row['conversation_id'],
            'message_id': row['message_id'],
            'seq': row['seq'],
            'raw_content': row['raw_content'],
            'content': row['content'],
            'result': row['result'],
            'create_time': row['create_time'],
        }
        for row in rows
    ]
