import lazyllm
from lazyllm import pipeline, bind
from chat.components.generate import AggregateComponent, RAGContextFormatter, CustomOutputParser
from chat.pipelines.builders import get_automodel
from chat.prompts.rag_answer import RAG_ANSWER_SYSTEM
from chat.config import LLM_TYPE_THINK

def _answer_llm():
    wrapped = get_automodel('qwen3_32b_custom', wrap_simple_llm=True)
    inner = wrapped.llm
    if getattr(inner, '_prompt', None) is not None:
        inner._prompt._set_model_configs(system=RAG_ANSWER_SYSTEM)
    return wrapped


def get_ppl_llm_generate(stream=False):
    with lazyllm.save_pipeline_result():
        with pipeline() as ppl:
            ppl.aggregate = AggregateComponent()
            ppl.formatter = RAGContextFormatter() | bind(query=ppl.kwargs['query'], nodes=ppl.aggregate)
            ppl.answer = _answer_llm() | \
                bind(stream=stream, llm_chat_history=[], files=[], priority=1)
            ppl.parser = CustomOutputParser(llm_type_think=LLM_TYPE_THINK) | bind(
                stream=stream,
                recall_result=ppl.input,
                aggregate=ppl.aggregate,
                image_files=[],
                debug=ppl.kwargs['debug'])

    return ppl
