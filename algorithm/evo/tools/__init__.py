"""
Tool registration.

Call ``register_all()`` once before using tools via LazyLLM ReactAgent.
Direct function calls (e.g. from pipeline) work without registration.
"""

_registered = False


def register_all() -> None:
    """Import all tool modules to trigger @fc_register decorators."""
    global _registered
    if _registered:
        return
    from evo.tools import evidence  # noqa: F401
    from evo.tools import data      # noqa: F401
    from evo.tools import stats     # noqa: F401
    from evo.tools import code      # noqa: F401
    from evo.tools import compare   # noqa: F401
    from evo.tools import cluster   # noqa: F401
    _registered = True
