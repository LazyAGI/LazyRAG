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
import concurrent.futures
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
    并行生成评测集主流程：
    - 支持：单跳、多跳、表格、公式 等任意任务扩展
    - 并行执行，速度翻倍
    - 最终自动凑够 100 题
    """
    log.info("开始生成评测集")

    def task_single():
        return generate_single_hop(
            prompt_generate_single_hop,
            TASK_SETTINGS["single_hop"]["num"],
            kb_id, algo_id, max_workers=5
        )

    def task_multi():
        return generate_multi_hop(kb_id)

    # 在这里继续加任务
    # def task_table(): return generate_table_questions(kb_id, algo_id)
    # def task_formula(): return generate_formula_questions(kb_id, algo_id)

    # 任务列表
    tasks = [
        ("单跳", task_single),
        ("多跳", task_multi),
        # ("表格", task_table),
        # ("公式", task_formula),
    ]

    log.info("开始并行执行所有生成任务...")
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_map = {executor.submit(task): name for name, task in tasks}
        for future in concurrent.futures.as_completed(future_map):
            task_name = future_map[future]
            try:
                res = future.result()
                log.info(f"✅ {task_name} 任务完成，生成 {len(res)} 条")
                all_results.extend(res)
            except Exception as e:
                log.error(f"❌ {task_name} 任务失败: {str(e)}")

    total = len(all_results)
    log.info(f"所有任务并行完成，总计生成: {total} 条")

    deficit = max(TOTAL_NUM - total, 0)
    if deficit > 0:
        log.info(f"需要补充 {deficit} 条单跳问题，确保达到 {TOTAL_NUM} 条")
        supplement = generate_single_hop(
            prompt_generate_single_hop, deficit, kb_id, algo_id, max_workers=5
        )
        all_results.extend(supplement)
        log.info(f"补充完成，最终总量: {len(all_results)} 条")

    all_results = all_results[:TOTAL_NUM]

    final_data = build_full_eval_set(
        qa_result=all_results,
        eval_name=eval_name,
        kb_id=kb_id,
    )
    file_path = write_full_eval_set(eval_name, final_data)

    log.info(f"评测集生成完成！文件路径：{file_path}，总题数：{len(all_results)}")
    return file_path, final_data

