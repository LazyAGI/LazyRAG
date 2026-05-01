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
        data_source: Optional custom data source (callable or list);
                     mainly for testing; omit to load from the database.
    """

    def __init__(self, create_user_id: str = '', *, data_source: Optional[Callable] = None) -> None:
        self._create_user_id = create_user_id
        self._lock = threading.RLock()
        actual_source = data_source if data_source is not None else self._load_from_db
        self._proc = QueryEnhACProcessor(
            data_source=actual_source,
            discriminator=None,
        )
        LOG.info(f'[VocabManager] initialized for create_user_id={create_user_id!r}, vocab_size={self.vocab_size}')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_from_db(self) -> List[dict]:
        """Load vocabulary rows for the current user from core.public.words;
        field format matches QueryEnhACProcessor."""
        return fetch_vocab_for_create_user_id(self._create_user_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> int:
        """Hot-reload: re-query vocabulary from the database and rebuild the AC automaton.

        Returns:
            Total number of words in the updated vocabulary.
        """
        with self._lock:
            self._proc.update_data_source(self._load_from_db)
            count = len(self._proc.word_to_cluster)
            LOG.info(f'[VocabManager] reloaded for create_user_id={self._create_user_id!r}, vocab_size={count}')
            return count

    def __call__(self, query: Union[str, list]) -> Union[str, list]:
        """Enhance the query using the vocabulary and return;
        returns as-is when vocabulary is empty or discriminator=None."""
        with self._lock:
            return self._proc(query)

    @property
    def vocab_size(self) -> int:
        """Number of words currently loaded."""
        with self._lock:
            return len(self._proc.word_to_cluster)

    @property
    def create_user_id(self) -> str:
        return self._create_user_id


# ---------------------------------------------------------------------------
# Multi-user registry (replaces the original module-level singleton)
# ---------------------------------------------------------------------------

_registry: dict = {}
_registry_lock = threading.Lock()


def get_vocab_manager(create_user_id: str = '') -> VocabManager:
    """Return the VocabManager for the given create_user_id (lazy init, one instance per create_user_id).

    Args:
        create_user_id: User identifier, corresponds to core.public.words.create_user_id.
                 Pass an empty string to get the default manager with no user filter (vocabulary is usually empty).
    """
    if create_user_id not in _registry:
        with _registry_lock:
            if create_user_id not in _registry:
                _registry[create_user_id] = VocabManager(create_user_id)
    return _registry[create_user_id]


def clear_registry() -> None:
    """Clear the registry (for testing only, to ensure isolation between test cases)."""
    with _registry_lock:
        _registry.clear()
