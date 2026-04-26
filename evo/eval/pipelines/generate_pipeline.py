from lazyllm import pipeline, parallel, loop
from services.chunk_service import get_doc_list, get_all_chunks_with_docid
from services.prompt_service import prompt_generate_single_hop, prompt_generate_multihop
from services.llm_service import chat
from config import TASK_SETTINGS,TOTAL_NUM
from utils.logger import log
from utils.checker import is_qa_json_valid
from services.graph_services import ParallelKGBuilder
from utils.writer import write_full_eval_set, build_full_eval_set
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

def generate_single_hop(p_func, count, kb_id, algo_id, max_workers=5):
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

            chunk_list = get_all_chunks_with_docid(kb_id, doc_id, algo_id)
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

def generate_multi_hop(kb_id):
    builder = ParallelKGBuilder()
    builder.build_global_graph_from_all_docs(kb_id)
    # 1. 跨文档多跳
    cross_list = builder.generate_multi_hop_questions(max_questions=20, cross_doc=True)
    # 2. 单文档同文件多跳
    single_list = builder.generate_multi_hop_questions(max_questions=20, cross_doc=False)
    questions = cross_list + single_list
    result_list = []
    for item in questions:
        result_list.append({"qa": item})

    return result_list


def run_generate_pipeline(kb_id, algo_id, eval_name):
    """
    生成评测集主流程：
    1. 生成单跳 + 多跳问题
    2. 不足 100 题则用单跳补齐
    3. 构建最终评测集并写入文件
    """
    log.info("开始生成评测集")

    result_single = generate_single_hop(
        prompt_generate_single_hop,
        TASK_SETTINGS["single_hop"]["num"],
        kb_id,
        algo_id,
        max_workers=5
    )
    result_multi = generate_multi_hop(kb_id)
    result = result_single + result_multi
    log.info(f"单跳生成 {len(result_single)} 条，多跳生成 {len(result_multi)} 条，总计 {len(result)} 条")

    # 2. 不足 TOTAL_NUM，则补充单跳
    deficit = TOTAL_NUM - len(result)
    if deficit > 0:
        log.info(f"总量不足 {TOTAL_NUM} 条，需补充 {deficit} 条单跳问题")
        supplementary = generate_single_hop(
            prompt_generate_single_hop,
            deficit,
            kb_id,
            algo_id,
            max_workers=5
        )
        result += supplementary
        log.info(f"补充完成，最终总量：{len(result)} 条")

    final_data = build_full_eval_set(
        qa_result=result,
        eval_name=eval_name,
        kb_id=kb_id,
    )
    file_path = write_full_eval_set(eval_name, final_data)

    log.info(f"评测集生成完成，保存路径：{file_path}")
    return file_path, final_data
