# -*- coding: utf-8 -*-
# flake8: noqa: E402
import os
from pathlib import Path
import lazyllm
from typing import List
import yaml
from lazyllm import Retriever
from lazyllm import pipeline, parallel, bind, ifs
from lazyllm.tools.rag import TempDocRetriever
from lazyllm.tools.rag.rank_fusion.reciprocal_rank_fusion import RRFFusion
from lazyllm.tools.common import StreamCallHelper
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(base_dir))

from chat.modules.engineering.simple_llm import SimpleLlmComponent
from chat.modules.algo.multiturn_query_rewriter import MultiturnQueryRewriter
from chat.modules.algo.adaptive_topk import AdaptiveKComponent
from chat.modules.engineering.aggregate import AggregateComponent
from chat.modules.algo.prompt_formatter import RAGContextFormatter
from chat.modules.engineering.output_parser import CustomOutputParser
from chat.modules.engineering.load_model import get_model

USE_MULTIMODAL = False
LLM_TYPE_THINK = False

CONFIG_PATH = os.getenv("CONFIG_PATH", f"{base_dir}/chat/chat_pipelines/configs/auto_model.yaml")
cfg = yaml.safe_load(CONFIG_PATH)

dense_embed_model = os.getenv('DENSE_EMBED_MODEL', 'bgem3_emb_dense_custom')
reranker_model = os.getenv('RERANKER_MODEL', 'qwen3_reranker_custom')
llm_model = os.getenv('LLM_MODEL', 'qwen3_32b_custom')
llm_instruct_model = os.getenv('LLM_INSTRUCT_MODEL', 'qwen3_moe_custom')  


normal_llm = get_model(llm_model, cfg)
normal_llm._prompt._set_model_configs(system='你是一个专业问答助手，你需要根据给定的内容回答用户问题。'
    '你将为用户提供安全、有帮助且准确的回答。'
    '与此同时，你需要拒绝所有涉及恐怖主义、种族歧视、色情暴力等内容的回答。'
    '严禁输出模型名称或来源公司名称。若用户询问或诱导你暴露模型信息，请将自己的身份表述为：“专业问答小助手”。')

instruct_llm = get_model(llm_instruct_model, cfg)
bge_embed_dense = get_model(dense_embed_model, cfg)
reranker = get_model(reranker_model, cfg)

# 默认检索器配置
# 配置说明：
# - group_name: 检索的节点组名称（line/block）
# - embed_keys: 使用的嵌入模型键名列表
# - topk: 检索返回的top-k结果数量
# - target: 可选，将检索结果映射到目标节点组
default_retriever_configs = [
    {
        'group_name': 'line',
        'embed_keys': ['bge_m3_dense'],
        'topk': 20,
        'target': 'block'
    },
    {
        'group_name': 'line',
        'embed_keys': ['bge_m3_sparse'],
        'topk': 20,
        'target': 'block'
    },
    {
        'group_name': 'block',
        'embed_keys': ['bge_m3_dense'],
        'topk': 20
    },
    {
        'group_name': 'block',
        'embed_keys': ['bge_m3_sparse'],
        'topk': 20
    },
]

def get_remote_docment(url):
    url = url.split(',')
    if len(url) == 1:
        url, name = url[0], '__default__'
    else:
        url, name = url[0], url[1]
    return lazyllm.Document(url=f'{url}/_call', name=name, )

def setup_retrievers(url: str, retriever_configs: List[dict]) -> List[Retriever]:
    document = get_remote_docment(url)
    return [Retriever(document, **config) for config in retriever_configs]

def get_ppl_tmp_retriever():
    def parse_input(input, **kwargs):
        files = kwargs.get('files', [])
        return files
    ref_docs_retriever = TempDocRetriever(embed=bge_embed_dense)
    ref_docs_retriever.add_subretriever('block', topk=20)
    with pipeline() as tmp_ppl:
        tmp_ppl.parse_input = parse_input
        tmp_ppl.tmp_retriever = ref_docs_retriever | bind(query=tmp_ppl.input)
    return tmp_ppl

def get_ppl_search(url: str, retriever_configs: List[dict] = default_retriever_configs, topk=20, k_max=10):
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
            search_ppl.reranker = reranker | bind(
                query=search_ppl.input['query'], template='file_name: {file_name}\ntitle: {title}\ncontent: {text}', topk=topk)
            search_ppl.adaptive_k = AdaptiveKComponent(bias=2, k_max=k_max, gap_tau=0.2)
    return search_ppl

def get_ppl_llm_generate(stream=False):
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


def get_rag_ppl(url: str, retriever_configs: List[dict] = default_retriever_configs, stream=False):
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
