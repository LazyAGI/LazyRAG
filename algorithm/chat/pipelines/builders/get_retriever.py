from copy import deepcopy
from typing import List, NamedTuple

from lazyllm import Retriever, bind, pipeline, Document
from lazyllm.tools.rag import TempDocRetriever

from chat.components.process.score_aware_aggregator import ScoreAwareParentAggregator
from chat.pipelines.builders.get_models import get_automodel
from chat.utils.load_config import get_retrieval_settings
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


def _build_kb_retriever(document: Document, cfg: dict):
    """Build a single kb retriever step from a config dict.

    If the config contains a 'target' key, the retriever is wrapped in a
    ScoreAwareParentAggregator so that child-node hit density is preserved
    when mapping to the parent group. Without this, lazyllm's internal
    find_parent deduplicates via a set and discards hit-count signal.
    """
    cfg = deepcopy(cfg)
    target = cfg.pop('target', None)
    retriever = Retriever(document, **cfg)
    if not target:
        return retriever
    aggregator = ScoreAwareParentAggregator(document=document, target_group=target)
    return pipeline(retriever, aggregator)


def get_retriever(url: str, retriever_configs: List[dict], *,
                  tmp_block_topk: int = DEFAULT_TMP_BLOCK_TOPK
                  ) -> SearchRetrievalParts:
    document = get_remote_docment(url)
    kb_retrievers = [_build_kb_retriever(document, cfg) for cfg in retriever_configs]

    settings = get_retrieval_settings()
    ref_docs_retriever = TempDocRetriever(embed=get_automodel(settings.temp_doc_embed_key))
    ref_docs_retriever.add_subretriever('block', topk=tmp_block_topk)
    with pipeline() as tmp_ppl:
        tmp_ppl.parse_input = lambda input, **kwargs: kwargs.get('files', [])
        tmp_ppl.tmp_retriever = ref_docs_retriever | bind(query=tmp_ppl.input)

    return SearchRetrievalParts(
        kb_retrievers=kb_retrievers,
        tmp_retriever_pipeline=tmp_ppl,
    )
