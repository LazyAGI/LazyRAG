from typing import List, NamedTuple, Optional

from lazyllm import AutoModel, Retriever, bind, pipeline, Document
from lazyllm.tools.rag import TempDocRetriever

from chat.config import DEFAULT_TMP_BLOCK_TOPK
from chat.utils.load_config import (
    get_config_path,
    get_image_embed_key,
    get_text_embed_keys,
)
from config import config as _cfg

# Primary dense embed role name — always the first text embed key in the config.
EMBED_MAIN = 'embed_main'


def _build_default_retriever_configs(topk: int = 20) -> List[dict]:
    '''Build retriever configs from the active text embed keys in the yaml config.

    Image embed (cross_modal_embed) is excluded — image retrieval is handled
    separately via the dedicated image_retriever returned by get_retriever().
    '''
    embed_keys = get_text_embed_keys() or [EMBED_MAIN]
    return [{'group_name': 'line', 'embed_keys': embed_keys, 'topk': topk, 'target': 'block'},
            {'group_name': 'block', 'embed_keys': embed_keys, 'topk': topk}]


class SearchRetrievalParts(NamedTuple):
    kb_retrievers: List[Retriever]
    tmp_retriever_pipeline: object
    image_retriever: Optional[Retriever]


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
    retriever_configs = retriever_configs or _build_default_retriever_configs()
    document = get_remote_docment(url)
    kb_retrievers = [Retriever(document, **cfg) for cfg in retriever_configs]

    image_retriever: Optional[Retriever] = None
    image_embed_key = get_image_embed_key()
    if image_embed_key:
        image_retriever = Retriever(
            document,
            group_name='image',
            embed_keys=[image_embed_key],
            topk=int(_cfg['image_topk']),
        )

    ref_docs_retriever = TempDocRetriever(embed=AutoModel(model=EMBED_MAIN, config=get_config_path()))
    ref_docs_retriever.add_subretriever('block', topk=tmp_block_topk)
    with pipeline() as tmp_ppl:
        tmp_ppl.parse_input = lambda input, **kwargs: kwargs.get('files', [])
        tmp_ppl.tmp_retriever = ref_docs_retriever | bind(query=tmp_ppl.input)

    return SearchRetrievalParts(
        kb_retrievers=kb_retrievers,
        tmp_retriever_pipeline=tmp_ppl,
        image_retriever=image_retriever,
    )
