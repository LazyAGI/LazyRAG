import json
import os
import requests
from services.llm_service import chat
from services.prompt_service import prompt_evaluate
from utils.logger import log
from config import DATA_PATH, CHAT_API


def call_rag_api(query):
    try:
        # mock 数据
        return {'code': 200, 'msg': 'success', 'trace_id': 'e02d7c25c9bd9ecaacf04','data': {'think': '', 'text': '编译原理、操作系统的知识', 'sources': [{'index': 3, 'number': 154, 'page': 63, 'bbox': [88, 234, 508, 750],'docid': 'doc_10b4ed1e02d7c25c9bd9ecaacf04aac2', 'kb_id': 'default','file_name': '21061-(6)-公共交通优先导向下的城市客运交通_同济大学.pdf','id': 'c114b524-adc2-4ea4-936b-35fc2d6bf5fb','text': '4.3 上海客运交通发展战略','group': 'block'}]}, 'cost': 36.6}
    except Exception as e:
        return {
            "rag_answer": f"RAG 接口请求失败：{str(e)}",
            "rag_reference": []
        }


def get_rag_response(query, url=CHAT_API, dataset_name='', is_debug=False, is_reasoning=False):
    # todo 改为真实调用
    data = {
        "query": query,
        "dataset": dataset_name,
        "debug": is_debug,
        "reasoning": is_reasoning
    }
    header = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        # with requests.Session() as session:
        # response = session.post(url, json=data, stream=True, headers=header)
        # text = response.content.decode('utf-8', errors='replace')
        # json_data = json.loads(text)

        # todo delete mock
        json_data = call_rag_api(query)

        trace_id = json_data["trace_id"]
        data = json_data["data"]
        answer = data["text"]

        """
        从JSON数据中提取sources数组内的所有text字段
        """
        text_list = []
        file_list = []
        chunk_ids = []
        doc_ids = []
        rag_response = json_data

        if 'sources' in data:
            for recall_item in data['sources']:
                if 'text' in recall_item:
                    text_list.append(recall_item['text'])
                if 'file_name' in recall_item:
                    file_list.append(recall_item['file_name'])
                if 'id' in recall_item:
                    chunk_ids.append(recall_item['id'])
                if 'docid' in recall_item:
                    doc_ids.append(recall_item['docid'])
    except Exception as e:
        log.error(f"请求失败: {e}")
        return []
    return [answer, text_list, file_list, rag_response, chunk_ids, doc_ids, trace_id]

def get_eval_queue(eval_name, case_id='',dataset_name=''):
    base_dir = DATA_PATH + f"/datasets/{eval_name}"
    eval_file = os.path.join(base_dir, "eval_data.json")

    with open(eval_file, "r", encoding="utf-8") as f:
        eval_data = json.load(f)

    cases = eval_data.get("cases", [])
    eval_queue = []

    if case_id:
        cases = [c for c in cases if c.get("case_id") == case_id]

    for case in cases:
        question = case["question"]
        ground_truth = case["ground_truth"]

        rag_response = get_rag_response(query=question,  dataset_name=dataset_name)
        # 计算召回率
        metrics = calculate_metrics(
            case["reference_chunk_ids"],
            case["reference_doc_ids"],
            rag_response[4],
            rag_response[5]
        )

        eval_queue.append({
            "case_id": case["case_id"],
            "key_points": case["key_points"],
            "question": question,
            "question_type": case["question_type"],
            "reference_chunk_ids": case["reference_chunk_ids"],
            "reference_doc_ids": case["reference_doc_ids"],
            "ground_truth": ground_truth,
            "rag_answer": rag_response[0],
            "retrieve_contexts": rag_response[1],
            "retrieve_doc": rag_response[2],
            "rag_response": rag_response[3],
            "retrieve_chunk_ids": rag_response[4],
            "retrieve_doc_ids": rag_response[5],
            "trace_id": rag_response[6],
            "context_recall": metrics['context_recall'],
            "doc_recall": metrics['doc_recall']
        })

    return {
        "eval_queue": eval_queue,
        "eval_set_id": eval_data.get("eval_set_id", ""),
        "kb_id": eval_data.get("kb_id", ""),
        "eval_name": eval_name
    }


def evaluate_answer(question, ground_truth, rag_answer, key_points, retrieve_contexts):
    prompt = prompt_evaluate(question, ground_truth, rag_answer, key_points, retrieve_contexts)
    try:
        res = chat(prompt)
        if isinstance(res, list):
            res = res[len(res) - 1]
        if isinstance(res, str):
            return json.loads(res)
        return res

    except Exception as e:
        log.info("解析异常", e)
        return {
            "answer_correctness": 0,
            "is_correct": False,
            "reason": "解析失败",
            "faithfulness": 0
        }


def calculate_metrics(reference_chunk_ids, reference_doc_ids, retrieve_chunk_ids, retrieve_doc_ids):
    """
    计算 RAG 检索效果：context_recall(chunk级) + doc_recall(文档级)
    """
    ref_chunks = set(reference_chunk_ids)
    ref_docs = set(reference_doc_ids)
    ret_chunks = set(retrieve_chunk_ids)
    ret_docs = set(retrieve_doc_ids)

    hit_chunks = len(ref_chunks & ret_chunks)
    hit_docs = len(ref_docs & ret_docs)

    context_recall = hit_chunks / len(ref_chunks) if ref_chunks else 0.0
    doc_recall = hit_docs / len(ref_docs) if ref_docs else 0.0

    return {
        "context_recall": round(context_recall, 4),
        "doc_recall": round(doc_recall, 4)
    }
