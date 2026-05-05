from typing import List, Any
import lazyllm
from lazyllm import pipeline, parallel, bind, ifs
from lazyllm.tools.rag import Reranker
from lazyllm.tools.rag.rank_fusion.reciprocal_rank_fusion import RRFFusion
from chat.components.process import AdaptiveKComponent, ContextExpansionComponent
from chat.pipelines.builders import get_automodel, get_retriever, get_remote_docment
from chat.utils.load_config import get_retrieval_settings


def parse_query(query_params=None, *_, **__) -> str:
    return query_params.get('query', '') if isinstance(query_params, dict) else ''


def has_files(_=None, x=None, *args, **kwargs) -> bool:
    if x is None:
        x = kwargs.get('x')
    if x is None:
        for arg in args:
            if isinstance(arg, dict):
                x = arg
                break
    return bool(isinstance(x, dict) and x.get('files'))


def merge_rank_results(*args):
    return tuple(rank_list for rank_list in args if rank_list)


def _adaptive_get_token_len(n: Any) -> int:
    txt = getattr(n, 'text', '') or ''
    return max(1, len(txt) // 4)


def get_ppl_search(url: str, retriever_configs: List[dict] = None, topk=20, k_max=10):
    if retriever_configs is None:
        retriever_configs = get_retrieval_settings().retriever_configs

    retrieval = get_retriever(url, retriever_configs)
    retrievers = retrieval.kb_retrievers
    tmp_retriever = retrieval.tmp_retriever_pipeline
    document = get_remote_docment(url)

    with lazyllm.save_pipeline_result():
        with pipeline() as search_ppl:
            search_ppl.parse_input = parse_query
            search_ppl.divert = ifs(
                has_files | bind(x=search_ppl.input),
                tpath=tmp_retriever | bind(files=search_ppl.input['files']),
                fpath=parallel(*[(retriever | bind(filters=search_ppl.input['filters'])) for retriever in retrievers])
            )
            search_ppl.merge_results = merge_rank_results
            search_ppl.join = RRFFusion(top_k=50)
            search_ppl.reranker = Reranker('ModuleReranker', model=get_automodel('reranker'), topk=topk) | bind(
                query=search_ppl.input['query']
            )
            search_ppl.adaptive_k = AdaptiveKComponent(bias=2, k_max=k_max, gap_tau=0.2,
                                                       get_token_len=_adaptive_get_token_len,
                                                       max_tokens=2048)
            search_ppl.ctx_expand = ContextExpansionComponent(
                document=document,
                token_budget=1500,
                score_decay=0.97,
                max_seeds=1
            )

    return search_ppl
