"""Compatibility shim -- delegates to the file-system implementation.

Historically this module owned a SQLite-backed task ledger; it now re-exports
the same surface from :mod:`evo.service.fs_state`. Callers keep using
``from evo.service import state`` unchanged; the only real difference is the
first parameter to each helper (``conn``) is now an ``FsStateStore`` instance
rather than a ``sqlite3.Connection``.
"""
from __future__ import annotations

from evo.service.fs_state import (  # noqa: F401
    APPLY_TERMINAL,
    FLOWS,
    FsStateStore,
    RUN_TERMINAL,
    StateError,
    append_round,
    create_task,
    get,
    has_active,
    latest_succeeded_run,
    list_recent,
    list_rounds,
    must_get,
    next_status,
    open_db,
    patch,
    signals,
    terminal_for,
    transition,
    update_round,
)

__all__ = [
    'APPLY_TERMINAL', 'FLOWS', 'FsStateStore', 'RUN_TERMINAL', 'StateError',
    'append_round', 'create_task', 'get', 'has_active', 'latest_succeeded_run',
    'list_recent', 'list_rounds', 'must_get', 'next_status', 'open_db',
    'patch', 'signals', 'terminal_for', 'transition', 'update_round',
]
