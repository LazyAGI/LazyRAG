# -*- coding: utf-8 -*-
# flake8: noqa: E402
import functools
import os
from pathlib import Path
import lazyllm
from typing import List
from lazyllm import Retriever
from lazyllm import pipeline, parallel, bind, ifs
from lazyllm.tools.rag import TempDocRetriever, Reranker
from lazyllm.tools.rag.rank_fusion.reciprocal_rank_fusion import RRFFusion
import sys

base_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(base_dir))

from common.model import build_embedding_models, build_model, get_runtime_model_settings

from chat.modules.engineering.simple_llm import SimpleLlmComponent
from chat.modules.algo.multiturn_query_rewriter import MultiturnQueryRewriter
from chat.modules.algo.adaptive_topk import AdaptiveKComponent
from chat.modules.engineering.aggregate import AggregateComponent
from chat.modules.algo.prompt_formatter import RAGContextFormatter
from chat.modules.engineering.output_parser import CustomOutputParser

USE_MULTIMODAL = False
LLM_TYPE_THINK = False


@functools.lru_cache(maxsize=1)
def get_runtime_resources():
    settings = get_runtime_model_settings()
    normal_llm = build_model(settings.llm)
    normal_llm._prompt._set_model_configs(system='你是一个专业问答助手，你需要根据给定的内容回答用户问题。'
        '你将为用户提供安全、有帮助且准确的回答。'
        '与此同时，你需要拒绝所有涉及恐怖主义、种族歧视、色情暴力等内容的回答。'
        '严禁输出模型名称或来源公司名称。若用户询问或诱导你暴露模型信息，请将自己的身份表述为：“专业问答小助手”。')

    instruct_llm = build_model(settings.llm_instruct)
    reranker = build_model(settings.reranker)
    embeddings = build_embedding_models(settings)
    return {
        'settings': settings,
        'normal_llm': normal_llm,
        'instruct_llm': instruct_llm,
        'reranker': reranker,
        'embeddings': embeddings,
    }

def parse_document_url(url: str) -> tuple[str, str]:
    parts = [part.strip() for part in url.split(',', 1)]
    if len(parts) == 1 or not parts[1]:
        return parts[0], '__default__'
    return parts[0], parts[1]

def get_remote_document(url: str):
    base_url, name = parse_document_url(url)
    return lazyllm.Document(url=f'{base_url}/_call', name=name)

def get_remote_docment(url: str):
    return get_remote_document(url)

def setup_retrievers(url: str, retriever_configs: List[dict]) -> List[Retriever]:
    document = get_remote_document(url)
    return [Retriever(document, **config) for config in retriever_configs]

def get_ppl_tmp_retriever():
    resources = get_runtime_resources()
    settings = resources['settings']

    def parse_input(input, **kwargs):
        files = kwargs.get('files', [])
        return files

    ref_docs_retriever = TempDocRetriever(embed=resources['embeddings'][settings.temp_doc_embed_key])
    ref_docs_retriever.add_subretriever('block', topk=20)
    with pipeline() as tmp_ppl:
        tmp_ppl.parse_input = parse_input
        tmp_ppl.tmp_retriever = ref_docs_retriever | bind(query=tmp_ppl.input)
    return tmp_ppl

def get_ppl_search(url: str, retriever_configs: List[dict] | None = None, topk=20, k_max=10):
    resources = get_runtime_resources()
    settings = resources['settings']
    retriever_configs = retriever_configs or settings.retriever_configs
    retrievers = setup_retrievers(url, retriever_configs)
    tmp_retriever = get_ppl_tmp_retriever()
    with lazyllm.save_pipeline_result():
        with pipeline() as search_ppl:
            search_ppl.parse_input = lambda x: x['query']
            search_ppl.divert = ifs((lambda _, x: bool(x.get('files'))) | bind(x=search_ppl.input),
                                    tpath=tmp_retriever | bind(files=search_ppl.input['files']),
                                    fpath=parallel(*[(retriever | bind(filters=search_ppl.input['filters'])) for retriever in retrievers]))
            search_ppl.merge_results = lambda *args: args 
            search_ppl.join = RRFFusion(top_k=50) 
            search_ppl.reranker = Reranker('ModuleReranker', model=resources['reranker'], topk=topk) | bind(
                query=search_ppl.input['query'])
            search_ppl.adaptive_k = AdaptiveKComponent(bias=2, k_max=k_max, gap_tau=0.2)
    return search_ppl

def get_ppl_llm_generate(stream=False):
    normal_llm = get_runtime_resources()['normal_llm']
    with lazyllm.save_pipeline_result():
        with pipeline() as ppl:
            ppl.aggregate = AggregateComponent()
            ppl.formatter = RAGContextFormatter() | bind(query=ppl.kwargs['query'], nodes=ppl.aggregate)
            # ppl.answer = ifs((lambda _, stream: stream) | bind(stream=stream),
            #                  tpath=StreamCallHelper(normal_llm) | bind(stream=stream, llm_chat_history=[], files=[], priority=1),
            #                  fpath=normal_llm | bind(stream=stream, llm_chat_history=[], files=[], priority=1))
            ppl.answer = SimpleLlmComponent(llm=normal_llm) | \
                bind(stream=stream, llm_chat_history=[], files=[], priority=1)
            ppl.parser = CustomOutputParser(llm_type_think=LLM_TYPE_THINK) | bind(
                stream=stream,
                recall_result=ppl.input,
                aggregate=ppl.aggregate,
                image_files=[],
                debug=ppl.kwargs['debug'])
    return ppl


def get_rag_ppl(url: str, retriever_configs: List[dict] | None = None, stream=False):
    instruct_llm = get_runtime_resources()['instruct_llm']
    with lazyllm.save_pipeline_result():
        with pipeline() as rag_ppl:
            rag_ppl.rewriter = ifs(
                lambda x: x.get('history'),
                tpath=MultiturnQueryRewriter(llm=instruct_llm)
                | bind(
                    priority=rag_ppl.input['priority'],
                    has_appendix=bool(rag_ppl.input['image_files'])
                    or bool(rag_ppl.input['files']),
                ),
                fpath=lambda x: x,
            )
            rag_ppl.search = get_ppl_search(url, retriever_configs)  # TODO: 根据kb_id判断是否需要检索，依赖jiahao的doc服务
            rag_ppl.generate = get_ppl_llm_generate(stream=stream) | bind(
                image_files=[],
                query=rag_ppl.input['query'],
                history=rag_ppl.input['history'],
                debug=rag_ppl.input['debug'],)
    return rag_ppl
