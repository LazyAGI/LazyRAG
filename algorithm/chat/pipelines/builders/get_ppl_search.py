from typing import List, Any
import lazyllm
from lazyllm import pipeline, parallel, bind, ifs
from lazyllm.tools.rag.rank_fusion.reciprocal_rank_fusion import RRFFusion
from chat.components.process import AdaptiveKComponent, ContextExpansionComponent
from chat.pipelines.builders import get_automodel, get_retriever, get_remote_docment
from chat.config import DEFAULT_RETRIEVER_CONFIGS


def _adaptive_get_token_len(n: Any) -> int:
    txt = getattr(n, 'text', '') or ''
    return max(1, len(txt) // 4)


def get_ppl_search(url: str, retriever_configs: List[dict] = None, topk=20, k_max=10):
    if retriever_configs is None:
        retriever_configs = DEFAULT_RETRIEVER_CONFIGS

    retrieval = get_retriever(url, retriever_configs)
    retrievers = retrieval.kb_retrievers
    tmp_retriever = retrieval.tmp_retriever_pipeline
    document = get_remote_docment(url)

    with lazyllm.save_pipeline_result():
        with pipeline() as search_ppl:
            search_ppl.parse_input = lambda x: x['query']
            search_ppl.divert = ifs(
                (lambda _, x: bool(x.get('files'))) | bind(x=search_ppl.input),
                tpath=tmp_retriever | bind(files=search_ppl.input['files']),
                fpath=parallel(*[(retriever | bind(filters=search_ppl.input['filters'])) for retriever in retrievers])
            )
            search_ppl.merge_results = lambda *args: args 
            search_ppl.join = RRFFusion(top_k=50) 
            search_ppl.reranker = get_automodel('qwen3_reranker_custom') | bind(
                query=search_ppl.input['query'], 
                template='file_name: {file_name}\ntitle: {title}\ncontent: {text}', 
                topk=topk
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
