from lazyllm import pipeline, parallel, loop
from services.chunk_service import get_doc_list, get_single_file_chunks
from services.prompt_service import prompt_generate_single_hop, prompt_generate_multihop
from services.llm_service import chat
from config import TASK_SETTINGS
from utils.logger import log
from utils.checker import is_qa_json_valid
from services.kg_services import ParallelKGBuilder
from utils.writer import write_full_eval_set, build_full_eval_set
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


def create_task_single_hop(p_func, count, kb_id, algo_id, max_workers=5):
    result_list = []
    lock = threading.Lock()
    max_retries = 100
    retry_count = 0
    last_log_percent = 0
    no_doc_flag = False

    def run_single():
        nonlocal no_doc_flag

        if no_doc_flag:
            return None

        try:
            doc_list = get_doc_list(kb_id, algo_id)

            if not doc_list:
                with lock:
                    no_doc_flag = True
                log.error("知识库内无文档，任务终止")
                return None

            selected_doc = random.choice(doc_list)["doc"]
            doc_id = selected_doc["doc_id"]
            filename = selected_doc.get("filename", "unknown.pdf")

            chunk_list = get_single_file_chunks(kb_id, doc_id, algo_id)
            valid_chunks = [c for c in chunk_list if len(c["content"]) > 50]
            if not valid_chunks:
                return None

            selected_chunk = random.choice(valid_chunks)
            chunk_id = selected_chunk["chunk_id"]
            prompt = p_func(selected_chunk["content"], filename, doc_id, chunk_id)

            try:
                qa_json = chat(prompt)
            except Exception as e:
                log.info(e)
                qa_json = {}

            if is_qa_json_valid(qa_json):
                qa_json["reference_doc_ids"] = [doc_id]
                qa_json["reference_chunk_ids"] = [chunk_id]
                return {"qa": qa_json}
            return None

        except Exception as e:
            log.error(f"生成异常: {str(e)}")
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(result_list) < count and retry_count < max_retries and not no_doc_flag:
            tasks = min(max_workers, count - len(result_list))
            futures = [executor.submit(run_single) for _ in range(tasks)]

            for f in futures:
                res = f.result()
                with lock:
                    if no_doc_flag:
                        break

                if res:
                    with lock:
                        if len(result_list) < count:
                            result_list.append(res)
                            current = len(result_list)
                            percent = int((current / count) * 100)
                            current_threshold = (percent // 25) * 25

                            if current_threshold > last_log_percent:
                                log.info(f"单跳生成进度：{current}/{count} ({current_threshold}%)")
                                last_log_percent = current_threshold
                else:
                    with lock:
                        retry_count += 1

            with lock:
                if no_doc_flag:
                    break

    log.info(f"单跳任务完成 | 总数：{len(result_list)} 条")
    return result_list

def create_task_multi_file(kb_id):
    builder = ParallelKGBuilder()
    builder.build_global_graph_from_all_docs(kb_id)
    questions = builder.generate_multi_file_questions(max_questions=300)
    result_list = []
    for item in questions:
        result_list.append({"qa": item})

    return result_list


def run_generate_pipeline(kb_id, algo_id, eval_name):
    # with pipeline() as ppl:
    #     ppl.all = parallel(
    #         create_task_single_hop(prompt_generate_single_hop, TASK_SETTINGS["single_hop"]["num"], kb_id, algo_id, max_workers=5)
    # create_task_multihop(kb_id, algo_id)
    # )
    # return ppl(None)
    log.info("开始生成评测集")
    result_single_hop = create_task_single_hop(prompt_generate_single_hop, TASK_SETTINGS["single_hop"]["num"], kb_id,
                                               algo_id,
                                               max_workers=5)
    result_multi_hop = create_task_multi_file(kb_id)
    result = result_single_hop + result_multi_hop
    final_data = build_full_eval_set(
        qa_result=result,
        eval_name=eval_name,
        kb_id=kb_id,
    )
    file_path = write_full_eval_set(eval_name, final_data)

    return file_path, final_data
