__all__ = [
    'agentic_rag',
]


def __getattr__(name: str):
    if name == 'agentic_rag':
        from chat.pipelines.agentic import agentic_rag
        return agentic_rag
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
