import lazyllm
from lazyllm import AutoModel, pipeline, bind
from lazyllm.module.servermodule import StreamCallHelper
from chat.components.generate import AggregateComponent, RAGContextFormatter, CustomOutputParser
from chat.prompts.rag_answer import RAG_ANSWER_SYSTEM
from chat.config import LLM_TYPE_THINK

_DEFAULT_LLM_KW = {
    'temperature': 0.01,
    'max_tokens': 4096,
    'frequency_penalty': 0,
}


def get_ppl_generate(stream=False):
    llm = AutoModel(model='llm', config=True).prompt(RAG_ANSWER_SYSTEM)

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

    with lazyllm.save_pipeline_result():
        with pipeline() as ppl:
            ppl.aggregate = AggregateComponent()
            ppl.formatter = RAGContextFormatter() | bind(query=ppl.kwargs['query'], nodes=ppl.aggregate)
            ppl.answer = llm_caller | bind(llm_chat_history=[], files=[], priority=1)
            ppl.parser = CustomOutputParser(llm_type_think=LLM_TYPE_THINK) | bind(
                stream=stream,
                recall_result=ppl.input,
                aggregate=ppl.aggregate,
                image_files=[],
                debug=ppl.kwargs['debug'])

    return ppl
