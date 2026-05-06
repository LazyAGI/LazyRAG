from typing import List, NamedTuple

from lazyllm import AutoModel, Retriever, bind, pipeline, Document
from lazyllm.tools.rag import TempDocRetriever

from chat.config import DEFAULT_TMP_BLOCK_TOPK
from chat.utils.load_config import get_embed_keys

# Primary dense embed role name — always the first embed key in the config.
EMBED_MAIN = 'embed_main'


def _build_default_retriever_configs(topk: int = 20) -> List[dict]:
    '''Build retriever configs from the active embed keys in the yaml config.

    Mirrors the original _build_default_retriever_configs logic: each embed key
    gets its own line-level and block-level group entry.  If embed_sparse is not
    present in the config it is simply omitted — sparse retrieval is optional.
    '''
    embed_keys = get_embed_keys()
    if not embed_keys:
        embed_keys = [EMBED_MAIN]
    configs = []
    for ek in embed_keys:
        configs.append({'group_name': 'line', 'embed_keys': [ek], 'topk': topk, 'target': 'block'})
    for ek in embed_keys:
        configs.append({'group_name': 'block', 'embed_keys': [ek], 'topk': topk})
    return configs


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
        retriever_configs = _build_default_retriever_configs()
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
