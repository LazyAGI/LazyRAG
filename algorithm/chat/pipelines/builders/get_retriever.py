from typing import List, NamedTuple

from lazyllm import AutoModel, Retriever, bind, pipeline, Document
from lazyllm.tools.rag import TempDocRetriever

from chat.config import DEFAULT_TMP_BLOCK_TOPK

# Embed role name — must match the key in runtime_models yaml.
EMBED_MAIN = 'embed_main'

# Default index parameters for the vector store.
DEFAULT_INDEX_KWARGS = {
    'index_type': 'IVF_FLAT',
    'metric_type': 'COSINE',
    'params': {'nlist': 128},
}

# Default retriever configs: line-level (targeting block) + block-level for embed_main.
DEFAULT_RETRIEVER_CONFIGS = [
    {'group_name': 'line', 'embed_keys': [EMBED_MAIN], 'topk': 20, 'target': 'block'},
    {'group_name': 'block', 'embed_keys': [EMBED_MAIN], 'topk': 20},
]


class SearchRetrievalParts(NamedTuple):
    kb_retrievers: List[Retriever]
    tmp_retriever_pipeline: object


def get_remote_docment(url: str) -> Document:
    url = url.split(',')
    if len(url) == 1:
        url, name = url[0], '__default__'
    else:
        url, name = url[0], url[1]
    return Document(url=f'{url}/_call', name=name)


def get_retriever(url: str, retriever_configs: List[dict] = None, *,
                  tmp_block_topk: int = DEFAULT_TMP_BLOCK_TOPK
                  ) -> SearchRetrievalParts:
    if retriever_configs is None:
        retriever_configs = DEFAULT_RETRIEVER_CONFIGS
    document = get_remote_docment(url)
    kb_retrievers = [Retriever(document, **cfg) for cfg in retriever_configs]

    ref_docs_retriever = TempDocRetriever(embed=AutoModel(model=EMBED_MAIN, config=True))
    ref_docs_retriever.add_subretriever('block', topk=tmp_block_topk)
    with pipeline() as tmp_ppl:
        tmp_ppl.parse_input = lambda input, **kwargs: kwargs.get('files', [])
        tmp_ppl.tmp_retriever = ref_docs_retriever | bind(query=tmp_ppl.input)

    return SearchRetrievalParts(
        kb_retrievers=kb_retrievers,
        tmp_retriever_pipeline=tmp_ppl,
    )
