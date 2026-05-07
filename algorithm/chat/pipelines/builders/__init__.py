from chat.pipelines.builders.get_retriever import get_retriever, get_remote_docment
from chat.pipelines.builders.get_ppl_search import get_ppl_search
from chat.pipelines.builders.get_ppl_generate import get_ppl_generate


def get_automodel(role: str):
    from lazyllm import AutoModel
    return AutoModel(model=role, config=True)


__all__ = [
    'get_retriever',
    'get_remote_docment',
    'get_ppl_search',
    'get_ppl_generate',
    'get_automodel',
]
