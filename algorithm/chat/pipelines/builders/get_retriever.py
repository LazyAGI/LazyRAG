from typing import List, NamedTuple
from lazyllm import Retriever, bind, pipeline, Document
from lazyllm.tools.rag import TempDocRetriever
from chat.pipelines.builders.get_models import get_automodel
from chat.config import DEFAULT_TMP_BLOCK_TOPK


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


def get_retriever(url: str, retriever_configs: List[dict], *,
                  tmp_block_topk: int = DEFAULT_TMP_BLOCK_TOPK
                  ) -> SearchRetrievalParts:
    document = get_remote_docment(url)
    kb_retrievers = [Retriever(document, **cfg) for cfg in retriever_configs]

    ref_docs_retriever = TempDocRetriever(embed=get_automodel('bgem3_emb_dense_custom'))
    ref_docs_retriever.add_subretriever('block', topk=tmp_block_topk)
    with pipeline() as tmp_ppl:
        tmp_ppl.parse_input = lambda input, **kwargs: kwargs.get('files', [])
        tmp_ppl.tmp_retriever = ref_docs_retriever | bind(query=tmp_ppl.input)

    return SearchRetrievalParts(
        kb_retrievers=kb_retrievers,
        tmp_retriever_pipeline=tmp_ppl,
    )
