from typing import List
import lazyllm
from lazyllm import AutoModel, pipeline, bind, ifs

from chat.pipelines.builders import get_ppl_search, get_ppl_generate
from chat.components.process.multiturn_query_rewriter import MultiturnQueryRewriter
from chat.components.process.query_image_rewriter import QueryImageRewriter
from chat.utils.load_config import get_config_path


def has_history(query_params=None, *_, **__) -> bool:
    return bool(isinstance(query_params, dict) and query_params.get('history'))


def keep_query_params(query_params=None, *_, **__):
    return query_params


def get_ppl_naive(url: str, retriever_configs: List[dict] = None, stream=False):

    with lazyllm.save_pipeline_result():
        with pipeline() as rag_ppl:
            rag_ppl.query_image_rewriter = QueryImageRewriter(
                llm=AutoModel(model='llm', config=get_config_path()),
            )
            rag_ppl.rewriter = ifs(
                has_history,
                tpath=MultiturnQueryRewriter(llm=AutoModel(model='llm_instruct', config=get_config_path()))
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
                query=rag_ppl.output('query_image_rewriter')['query'],
                history=rag_ppl.input['history'],
                debug=rag_ppl.input['debug'],)

    return rag_ppl

if __name__ == "__main__":
    # import lazyllm
    # def get_remote_docment(url, name="__default__"):
    #     return lazyllm.Document(url=f"{url}/_call", name=name)

    # url = "http://10.119.16.66:9012,tyy_0302"
    # url="http://10.119.16.66:9003,research_center_0131_a"
    # url = "http://10.119.16.66:9102,quantum_0131_a"
    # url = "http://127.0.0.1:28055"
    # algo 
    url = 'http://127.0.0.1:28000,general_algo'
    rag_ppl = get_ppl_naive(url, stream=False)
    params = {
        "filters": {},
        "query": "what's color of the cat", 
        "files": [],
        "history": [],
        "debug": False,
        "query_images": [
        "/home/sensetime/cuishaoting/safe_home/LazyRAG/test_doc/cat.jpg"
    ]
    }
    result = rag_ppl(params)
    print(result['sources'])
    print('--------------------------------')
    print(result['text'])
