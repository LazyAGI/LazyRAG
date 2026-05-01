"""VocabManager: Multi-user vocabulary manager wrapping QueryEnhACProcessor with hot-reload support.

Each user (create_user_id) maintains an independent QueryEnhACProcessor instance.
Vocabulary data is queried from the backend-managed PostgreSQL core.public.words table
by create_user_id.

Usage:
    # Backend notifies the algorithm service to hot-reload a user's vocabulary
    get_vocab_manager('user_001').reload()

    # Enhance a query with the vocabulary before retrieval (used in pipeline)
    enhanced = get_vocab_manager('user_001')('user query text')

Environment variables:
    LAZYRAG_CORE_DATABASE_URL / ACL_DB_DSN  core database connection
    LAZYRAG_DATABASE_URL                     fallback connection
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional, Union

from lazyllm import LOG
from lazyllm.tools.rag.query_enh_ac import QueryEnhACProcessor

from .db import fetch_vocab_for_create_user_id


class VocabManager:
    """Single-user vocabulary manager: bound to one create_user_id, loads vocabulary from DB, supports hot-reload.

    Args:
        create_user_id: User identifier (corresponds to core.public.words.create_user_id).
                        Pass None or '' to load the global vocabulary (no user filter).
        db_url: Optional explicit database connection URL; falls back to environment variables if not provided.
    """

    def __init__(
        self,
        create_user_id: Optional[str] = None,
        db_url: Optional[str] = None,
    ) -> None:
        self._create_user_id = create_user_id or None
        self._db_url = db_url
        self._lock = threading.Lock()
        self._processor: Optional[QueryEnhACProcessor] = None
        self._vocab_size: int = 0
        self.reload()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload vocabulary from the database and rebuild the AC automaton."""
        rows = fetch_vocab_for_create_user_id(
            create_user_id=self._create_user_id,
            db_url=self._db_url,
        )
        synonyms: List[List[str]] = [r['synonyms'] for r in rows if r.get('synonyms')]
        with self._lock:
            self._processor = QueryEnhACProcessor(synonyms)
            self._vocab_size = len(synonyms)
        LOG.info(
            f'[VocabManager] Reloaded create_user_id={self._create_user_id!r} '
            f'vocab_size={self._vocab_size}'
        )

    def __call__(self, query: Union[str, dict], *args, **kwargs) -> Union[str, dict]:
        """Enhance the query using the vocabulary (AC automaton synonym replacement).

        Accepts either a plain string or a dict with a 'query' key.
        Returns the same type as the input.
        """
        with self._lock:
            processor = self._processor
        if processor is None:
            return query
        if isinstance(query, dict):
            raw = query.get('query', '')
            enhanced = processor(raw) if raw else raw
            if enhanced != raw:
                query = dict(query)
                query['query'] = enhanced
            return query
        return processor(query)

    @property
    def vocab_size(self) -> int:
        return self._vocab_size


# ------------------------------------------------------------------
# Global registry
# ------------------------------------------------------------------

_registry: dict[Optional[str], VocabManager] = {}
_registry_lock = threading.Lock()


def get_vocab_manager(
    create_user_id: Optional[str] = None,
    factory: Optional[Callable[[], VocabManager]] = None,
) -> VocabManager:
    """Return the VocabManager for the given user, creating one if it does not exist."""
    key = (create_user_id or '').strip() or None
    with _registry_lock:
        if key not in _registry:
            _registry[key] = factory() if factory else VocabManager(key)
    return _registry[key]


def clear_registry() -> None:
    """Clear the registry (for testing only, to ensure isolation between test cases)."""
    with _registry_lock:
        _registry.clear()
