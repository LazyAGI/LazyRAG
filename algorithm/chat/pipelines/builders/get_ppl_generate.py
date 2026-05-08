import lazyllm
from lazyllm import AutoModel, pipeline, bind, ifs
from lazyllm.module.servermodule import StreamCallHelper
from chat.components.generate import AggregateComponent, RAGContextFormatter, CustomOutputParser
from chat.prompts.rag_answer import RAG_ANSWER_SYSTEM
from chat.config import LLM_TYPE_THINK
from chat.utils.load_config import get_config_path
from chat.utils.generate_pipeline_helpers import (
    _has_image_nodes,
    _merge_text_and_images,
    _text_nodes,
    build_multimodal_query_with_images,
)

_DEFAULT_LLM_KW = {
    'temperature': 0.01,
    'max_tokens': 4096,
    'frequency_penalty': 0,
}


def _build_llm_caller(stream: bool):
    llm = AutoModel(model='llm', config=get_config_path()).prompt(RAG_ANSWER_SYSTEM)
    if stream:
        def llm_caller(query, llm_chat_history=None, files=None, **kw):
            shared = llm.share()
            return StreamCallHelper(shared).astream(
                query,
                llm_chat_history=llm_chat_history or [],
                lazyllm_files=files[:2] if files else None,
                **{**_DEFAULT_LLM_KW, **kw},
            )
    else:
        def llm_caller(query, llm_chat_history=None, files=None, **kw):
            shared = llm.share()
            return shared(
                query,
                stream_output=False,
                llm_chat_history=llm_chat_history or [],
                lazyllm_files=files[:2] if files else None,
                **{**_DEFAULT_LLM_KW, **kw},
            )
    return llm_caller


def get_ppl_generate(stream=False):
    llm_caller = _build_llm_caller(stream)

    with lazyllm.save_pipeline_result():
        with pipeline() as ppl:
            with pipeline() as mixed_aggregate:
                mixed_aggregate.text_nodes = _text_nodes
                mixed_aggregate.text_aggregate = AggregateComponent()
                mixed_aggregate.merge_images = _merge_text_and_images | bind(all_nodes=mixed_aggregate.input)
            ppl.aggregate = ifs(_has_image_nodes, tpath=mixed_aggregate, fpath=AggregateComponent())
            ppl.formatter = RAGContextFormatter() | bind(query=ppl.kwargs['query'], nodes=ppl.aggregate)
            ppl.multimodal_query = build_multimodal_query_with_images | bind(nodes=ppl.aggregate)
            ppl.answer = llm_caller | bind(llm_chat_history=[], files=[], priority=1)
            ppl.parser = CustomOutputParser(llm_type_think=LLM_TYPE_THINK) | bind(
                stream=stream,
                recall_result=ppl.input,
                aggregate=ppl.aggregate,
                image_files=[],
                debug=ppl.kwargs['debug'])

    return ppl
