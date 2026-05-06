from typing import List
import lazyllm
from lazyllm import AutoModel, pipeline, bind, ifs

from chat.pipelines.builders import get_ppl_search, get_ppl_generate
from chat.components.process.multiturn_query_rewriter import MultiturnQueryRewriter
from chat.pipelines.builders.get_retriever import DEFAULT_RETRIEVER_CONFIGS


def has_history(query_params=None, *_, **__) -> bool:
    return bool(isinstance(query_params, dict) and query_params.get('history'))


def keep_query_params(query_params=None, *_, **__):
    return query_params


def get_ppl_naive(url: str, retriever_configs: List[dict] = None, stream=False):
    if retriever_configs is None:
        retriever_configs = DEFAULT_RETRIEVER_CONFIGS

    with lazyllm.save_pipeline_result():
        with pipeline() as rag_ppl:
            rag_ppl.rewriter = ifs(
                has_history,
                tpath=MultiturnQueryRewriter(llm=AutoModel(model='llm_instruct', config=True))
                | bind(
                    priority=rag_ppl.input['priority'],
                    has_appendix=bool(rag_ppl.input['image_files'])
                    or bool(rag_ppl.input['files']),
                ),
                fpath=keep_query_params,
            )
            rag_ppl.search = get_ppl_search(url, retriever_configs)
            rag_ppl.generate = get_ppl_generate(stream=stream) | bind(
                image_files=[],
                query=rag_ppl.input['query'],
                history=rag_ppl.input['history'],
                debug=rag_ppl.input['debug'],)

    return rag_ppl
